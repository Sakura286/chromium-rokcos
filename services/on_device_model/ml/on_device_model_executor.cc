// Copyright 2023 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "services/on_device_model/ml/on_device_model_executor.h"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "base/check.h"
#include "base/compiler_specific.h"
#include "base/containers/unique_ptr_adapters.h"
#include "base/logging.h"
#include "base/memory/raw_ref.h"
#include "base/memory/scoped_refptr.h"
#include "base/memory/weak_ptr.h"
#include "base/metrics/field_trial_params.h"
#include "base/metrics/histogram_functions.h"
#include "base/numerics/safe_conversions.h"
#include "base/task/thread_pool.h"
#include "base/timer/elapsed_timer.h"
#include "components/optimization_guide/core/optimization_guide_features.h"
#include "services/on_device_model/ml/chrome_ml.h"
#include "services/on_device_model/ml/session_accessor.h"
#include "services/on_device_model/public/mojom/on_device_model.mojom.h"
#include "services/on_device_model/public/mojom/on_device_model_service.mojom.h"

#if BUILDFLAG(IS_MAC)
#include "base/apple/foundation_util.h"
#endif

using on_device_model::mojom::LoadModelResult;

namespace ml {
namespace {

constexpr uint32_t kReserveTokensForSafety = 2;

const base::FeatureParam<bool> kPreferTextureWeights{
    &optimization_guide::features::kOptimizationGuideOnDeviceModel,
    "on_device_model_prefer_texture_weights", true};

const base::FeatureParam<bool> kEnableHostMappedPointer{
    &optimization_guide::features::kOptimizationGuideOnDeviceModel,
    "on_device_model_enable_host_mapped_pointer", true};

const base::FeatureParam<bool> kUseLowPower{
    &optimization_guide::features::kOptimizationGuideOnDeviceModel,
    "on_device_model_use_low_power", false};

const base::FeatureParam<bool> kAllowFp16{
    &optimization_guide::features::kOptimizationGuideOnDeviceModel,
    "on_device_model_allow_fp16", true};

// Helper to bind object methods as weak task-posting callback functions.
template <typename R, typename C, typename... Args>
std::function<R(Args...)> CreateWeakCallbackFn(R (C::*method)(Args...),
                                               C* that) {
  return [weak_ptr = that->AsWeakPtr(), method,
          task_runner =
              base::SequencedTaskRunner::GetCurrentDefault()](Args&&... args) {
    task_runner->PostTask(
        FROM_HERE,
        base::BindOnce(method, weak_ptr, std::forward<Args>(args)...));
  };
}

// Helper to convert a OnceCallback to std::function.
template <typename R, typename... Args>
std::function<R(Args...)> ConvertCallbackToFn(
    base::OnceCallback<R(Args...)> callback) {
  auto shared_callback =
      std::make_shared<base::OnceCallback<R(Args...)>>(std::move(callback));
  return [shared_callback = shared_callback,
          task_runner =
              base::SequencedTaskRunner::GetCurrentDefault()](Args&&... args) {
    if (!shared_callback->is_null()) {
      task_runner->PostTask(FROM_HERE,
                            base::BindOnce(std::move(*shared_callback),
                                           std::forward<Args>(args)...));
    }
  };
}

int CalculateTokensPerSecond(int num_tokens, base::TimeDelta duration) {
  if (duration.InMicroseconds() <= 0) {
    return 0;
  }
  return (num_tokens / static_cast<float>(duration.InMicroseconds())) *
         base::Time::kMicrosecondsPerSecond;
}

float GetTemperature(std::optional<float> temperature) {
  return std::max(0.0f, temperature.value_or(0.0f));
}

uint32_t GetTopK(std::optional<uint32_t> top_k) {
  return std::min(static_cast<uint32_t>(
                      optimization_guide::features::GetOnDeviceModelMaxTopK()),
                  std::max(1u, top_k.value_or(1)));
}

// Handles sending and canceling responses.
class Responder final {
 public:
  explicit Responder(
      mojo::PendingRemote<on_device_model::mojom::StreamingResponder> responder,
      base::OnceClosure on_complete,
      SessionAccessor::Ptr session)
      : responder_(std::move(responder)),
        on_complete_(std::move(on_complete)),
        session_(std::move(session)) {
    responder_.set_disconnect_handler(
        base::BindOnce(&Responder::Cancel, base::Unretained(this)));
  }
  ~Responder() { Cancel(); }

  ChromeMLCancelFn* GetCancelFn() { return &cancel_; }

  ChromeMLExecutionOutputFn CreateOutputFn() {
    return [weak_ptr = weak_ptr_factory_.GetWeakPtr(),
            task_runner = base::SequencedTaskRunner::GetCurrentDefault()](
               const ChromeMLExecutionOutput* output) {
      std::optional<std::string> text;
      switch (output->status) {
        case ChromeMLExecutionStatus::kInProgress:
          CHECK(output->text);
          text.emplace(output->text);
          break;
        case ChromeMLExecutionStatus::kComplete:
          DCHECK(!output->text);
          break;
      }

      task_runner->PostTask(
          FROM_HERE,
          base::BindOnce(&Responder::OnOutput, weak_ptr, std::move(text)));
    };
  }

 private:
  void OnOutput(std::optional<std::string> text) {
    if (text) {
      num_tokens_++;
      output_so_far_ += *text;
      if (first_token_time_ == base::TimeTicks()) {
        first_token_time_ = base::TimeTicks::Now();
      }

      auto chunk = on_device_model::mojom::ResponseChunk::New();
      chunk->text = *text;
      responder_->OnResponse(std::move(chunk));
    } else {
      // Empty text means the output is finished. Delete the session immediately
      // to free up any resources.
      session_ = nullptr;
      base::UmaHistogramCounts10000("OnDeviceModel.TokenCount.Output",
                                    num_tokens_);
      if (num_tokens_ > 1) {
        // Time starts at the first token to avoid counting input processing
        // time, so calculate using num_tokens_ - 1.
        base::UmaHistogramCounts1000(
            "OnDeviceModel.TokensPerSecond.Output",
            CalculateTokensPerSecond(
                num_tokens_ - 1, base::TimeTicks::Now() - first_token_time_));
      }

      auto summary = on_device_model::mojom::ResponseSummary::New();
      responder_->OnComplete(std::move(summary));
      if (!on_complete_.is_null()) {
        std::move(on_complete_).Run();
      }
    }
  }

  void Cancel() {
    session_ = nullptr;
    if (cancel_) {
      cancel_();
    }
    if (!on_complete_.is_null()) {
      std::move(on_complete_).Run();
    }
  }

  base::TimeTicks first_token_time_;
  int num_tokens_ = 0;
  std::string output_so_far_;
  mojo::Remote<on_device_model::mojom::StreamingResponder> responder_;
  ChromeMLCancelFn cancel_;
  base::OnceClosure on_complete_;
  SessionAccessor::Ptr session_;
  base::WeakPtrFactory<Responder> weak_ptr_factory_{this};
};

// Handles calling the ContextClient on completion and canceling the context
// request.
class ContextHolder final {
 public:
  explicit ContextHolder(
      mojo::PendingRemote<on_device_model::mojom::ContextClient> client,
      base::OnceCallback<void(ContextHolder*)> on_disconnect,
      base::OnceClosure on_complete)
      : client_(std::move(client)),
        on_disconnect_(std::move(on_disconnect)),
        on_complete_(std::move(on_complete)) {
    if (client_) {
      client_.set_disconnect_handler(
          base::BindOnce(&ContextHolder::OnDisconnect, base::Unretained(this)));
    }
  }
  ~ContextHolder() {
    if (cancel_) {
      cancel_();
    }
    if (!on_complete_.is_null()) {
      std::move(on_complete_).Run();
    }
  }

  ChromeMLCancelFn* GetCancelFn() { return &cancel_; }

  ChromeMLContextSavedFn CreateContextSavedFn() {
    return CreateWeakCallbackFn(&ContextHolder::OnComplete, this);
  }

  base::WeakPtr<ContextHolder> AsWeakPtr() {
    return weak_ptr_factory_.GetWeakPtr();
  }

 private:
  void OnComplete(int tokens_processed) {
    if (tokens_processed > 0) {
      base::UmaHistogramCounts10000("OnDeviceModel.TokenCount.Context",
                                    tokens_processed);
      base::UmaHistogramCounts10000(
          "OnDeviceModel.TokensPerSecond.Context",
          CalculateTokensPerSecond(tokens_processed, timer_.Elapsed()));
    }
    if (client_) {
      client_->OnComplete(tokens_processed);
    }
    if (!on_complete_.is_null()) {
      std::move(on_complete_).Run();
    }
    OnDisconnect();
  }

  void OnDisconnect() {
    if (on_disconnect_) {
      std::move(on_disconnect_).Run(this);
    }
    // this may be deleted.
  }

  base::ElapsedTimer timer_;
  mojo::Remote<on_device_model::mojom::ContextClient> client_;
  base::OnceCallback<void(ContextHolder*)> on_disconnect_;
  ChromeMLCancelFn cancel_;
  base::OnceClosure on_complete_;
  base::WeakPtrFactory<ContextHolder> weak_ptr_factory_{this};
};

class SessionImpl : public on_device_model::OnDeviceModel::Session {
 public:
  SessionImpl(const ChromeML& chrome_ml,
              ChromeMLModel model,
              SessionAccessor::Ptr session,
              SessionAccessor::Ptr empty_session,
              uint32_t max_tokens,
              std::optional<uint32_t> adaptation_id)
      : chrome_ml_(chrome_ml),
        model_(model),
        session_(std::move(session)),
        empty_session_(std::move(empty_session)),
        max_tokens_(max_tokens),
        adaptation_id_(adaptation_id) {}
  ~SessionImpl() override = default;

  SessionImpl(const SessionImpl&) = delete;
  SessionImpl& operator=(const SessionImpl&) = delete;

  DISABLE_CFI_DLSYM
  void AddContext(
      on_device_model::mojom::InputOptionsPtr input,
      mojo::PendingRemote<on_device_model::mojom::ContextClient> client,
      base::OnceClosure on_complete) override {
    auto context_holder = std::make_unique<ContextHolder>(
        std::move(client),
        base::BindOnce(&SessionImpl::RemoveContext, base::Unretained(this)),
        std::move(on_complete));
    input->max_tokens =
        std::min(input->max_tokens.value_or(max_tokens_), max_tokens_);
    input->top_k = GetTopK(input->top_k);
    input->temperature = GetTemperature(input->temperature);
    ChromeMLContextSavedFn context_saved_fn =
        context_holder->CreateContextSavedFn();
    *context_holder->GetCancelFn() =
        session_->Execute(std::move(input), nullptr, context_saved_fn);
    context_holders_.insert(std::move(context_holder));
  }

  DISABLE_CFI_DLSYM
  void Execute(
      on_device_model::mojom::InputOptionsPtr input,
      mojo::PendingRemote<on_device_model::mojom::StreamingResponder> response,
      base::OnceClosure on_complete) override {
    auto cloned =
        input->ignore_context ? empty_session_->Clone() : session_->Clone();
    auto cloned_raw = cloned.get();  // For Execute after std::move
    responder_ = std::make_unique<Responder>(
        std::move(response), std::move(on_complete), std::move(cloned));
    ChromeMLExecutionOutputFn output_fn = responder_->CreateOutputFn();
    input->max_tokens =
        std::min(input->max_tokens.value_or(max_tokens_), max_tokens_);
    input->top_k = GetTopK(input->top_k);
    input->temperature = GetTemperature(input->temperature);
    *responder_->GetCancelFn() =
        cloned_raw->Execute(std::move(input), output_fn, nullptr);
  }

  DISABLE_CFI_DLSYM
  void SizeInTokens(const std::string& text,
                    base::OnceCallback<void(uint32_t)> callback) override {
      session_->SizeInTokens(text, ConvertCallbackToFn(std::move(callback)));
  }

  DISABLE_CFI_DLSYM
  void Score(const std::string& text,
             base::OnceCallback<void(float)> callback) override {
    session_->Score(text, ConvertCallbackToFn(std::move(callback)));
  }

  std::unique_ptr<Session> Clone() override {
    return std::make_unique<SessionImpl>(
        chrome_ml_.get(), model_, session_->Clone(), empty_session_->Clone(),
        max_tokens_, adaptation_id_);
  }

 private:
  void RemoveContext(ContextHolder* context) {
    std::erase_if(context_holders_, base::MatchesUniquePtr(context));
  }

  const raw_ref<const ChromeML> chrome_ml_;
  ChromeMLModel model_;
  SessionAccessor::Ptr session_;
  SessionAccessor::Ptr empty_session_;
  const uint32_t max_tokens_;
  std::unique_ptr<Responder> responder_;
  std::set<std::unique_ptr<ContextHolder>> context_holders_;
  std::optional<uint32_t> adaptation_id_;
};

DISABLE_CFI_DLSYM
void DestroyModel(const ChromeML* chrome_ml, ChromeMLModel model) {
  chrome_ml->api().DestroyModel(model);
}

}  // namespace

OnDeviceModelExecutor::OnDeviceModelExecutor(
    base::PassKey<OnDeviceModelExecutor>,
    const ChromeML& chrome_ml)
    : chrome_ml_(chrome_ml),
      task_runner_(base::SequencedTaskRunner::GetCurrentDefault()),
      model_task_runner_(
          base::ThreadPool::CreateSequencedTaskRunner({base::MayBlock()})) {}

OnDeviceModelExecutor::~OnDeviceModelExecutor() {
  if (model_ != 0) {
    model_task_runner_->PostTask(
        FROM_HERE, base::BindOnce(&DestroyModel, &chrome_ml_.get(), model_));
  }
}

// static
base::expected<std::unique_ptr<OnDeviceModelExecutor>, LoadModelResult>
OnDeviceModelExecutor::CreateWithResult(
    const ChromeML& chrome_ml,
    on_device_model::mojom::LoadModelParamsPtr params,
    base::OnceClosure on_complete) {
  auto executor = std::make_unique<OnDeviceModelExecutor>(
      base::PassKey<OnDeviceModelExecutor>(), chrome_ml);
  auto load_model_result =
      executor->Init(std::move(params), std::move(on_complete));
  if (load_model_result == LoadModelResult::kSuccess) {
    return base::ok<std::unique_ptr<OnDeviceModelExecutor>>(
        std::move(executor));
  }
  return base::unexpected(load_model_result);
}

std::unique_ptr<on_device_model::OnDeviceModel::Session>
OnDeviceModelExecutor::CreateSession(std::optional<uint32_t> adaptation_id) {
  auto it = base_sessions_.find(adaptation_id);
  CHECK(it != base_sessions_.end());
  return std::make_unique<SessionImpl>(
      *chrome_ml_, model_, it->second->Clone(), it->second->Clone(),
      max_tokens_ - kReserveTokensForSafety, adaptation_id);
}

void OnDeviceModelExecutor::DetectLanguage(
    const std::string& text,
    on_device_model::mojom::OnDeviceModel::DetectLanguageCallback callback) {
  if (!ts_model_) {
    std::move(callback).Run(nullptr);
    return;
  }
  ts_model_.AsyncCall(&TsModel::DetectLanguage)
      .WithArgs(text)
      .Then(std::move(callback));
}

DISABLE_CFI_DLSYM
void OnDeviceModelExecutor::ClassifyTextSafety(
    const std::string& text,
    on_device_model::mojom::OnDeviceModel::ClassifyTextSafetyCallback
        callback) {
  if (!ts_model_) {
    std::move(callback).Run(nullptr);
    return;
  }
  ts_model_.AsyncCall(&TsModel::ClassifyTextSafety)
      .WithArgs(text)
      .Then(std::move(callback));
}

DISABLE_CFI_DLSYM
base::expected<uint32_t, LoadModelResult> OnDeviceModelExecutor::LoadAdaptation(
    on_device_model::mojom::LoadAdaptationParamsPtr params,
    base::OnceClosure on_complete) {
  on_device_model::AdaptationAssets assets = std::move(params->assets);
  static uint32_t next_id = 0;
  base_sessions_.insert(
      {next_id, SessionAccessor::Create(chrome_ml_.get(), model_task_runner_,
                                        model_, std::move(assets.weights))});
  model_task_runner_->PostTask(FROM_HERE, std::move(on_complete));
  return base::ok(next_id++);
}

DISABLE_CFI_DLSYM
LoadModelResult OnDeviceModelExecutor::Init(
    on_device_model::mojom::LoadModelParamsPtr params,
    base::OnceClosure on_complete) {
  on_device_model::ModelAssets assets = std::move(params->assets);

  on_device_model::mojom::ModelAssetsPtr ts_assets;
  if (assets.ts_data.IsValid()) {
    ts_assets = on_device_model::mojom::ModelAssets::New();
    ts_assets->ts_data = std::move(assets.ts_data);
    ts_assets->ts_sp_model = std::move(assets.ts_sp_model);
  }

  if (ts_assets || assets.language_detection_model.IsValid()) {
    ts_model_ = TsModel::Create(*chrome_ml_, std::move(ts_assets),
                                std::move(assets.language_detection_model));
    if (!ts_model_) {
      LOG(ERROR) << "Invalid TS model data supplied";
      return LoadModelResult::kFailedToLoadLibrary;
    }
  }

  max_tokens_ = std::max(params->max_tokens, kReserveTokensForSafety);

  ChromeMLModelData data = {
      .weights_file = assets.weights.TakePlatformFile(),
  };
  ChromeMLModelDescriptor descriptor = {
      .model_data = &data,
      .max_tokens = max_tokens_,
      .temperature = 0.0f,
      .top_k = optimization_guide::features::GetOnDeviceModelMaxTopK(),
      .adaptation_ranks = params->adaptation_ranks.data(),
      .adaptation_ranks_size = params->adaptation_ranks.size(),
      .prefer_texture_weights = kPreferTextureWeights.Get(),
      .enable_host_mapped_pointer = kEnableHostMappedPointer.Get(),
      .use_low_power = kUseLowPower.Get(),
      .allow_fp16 = kAllowFp16.Get(),
  };
  model_ = chrome_ml_->api().SessionCreateModel(
      &descriptor, reinterpret_cast<uintptr_t>(this),
      OnDeviceModelExecutor::Schedule);
  if (model_) {
    base_sessions_.insert(
        {std::nullopt, SessionAccessor::Create(chrome_ml_.get(),
                                               model_task_runner_, model_)});
  }
  model_task_runner_->PostTask(FROM_HERE, std::move(on_complete));
  return (model_ != 0) ? LoadModelResult::kSuccess
                       : LoadModelResult::kFailedToLoadLibrary;
}

// static
void OnDeviceModelExecutor::Schedule(uintptr_t context,
                                     std::function<void()>* fn) {
  base::ThreadPool::PostTask(
      FROM_HERE, {base::TaskPriority::USER_BLOCKING, base::MayBlock()},
      base::BindOnce([](std::function<void()> fn) { fn(); }, std::move(*fn)));
}

}  // namespace ml
