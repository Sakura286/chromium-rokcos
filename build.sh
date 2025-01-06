#!/bin/bash

gn gen out/Release-riscv64 --args='
is_official_build=true
is_debug=false
is_clang=true
target_cpu="riscv64"
treat_warnings_as_errors=false
chrome_pgo_phase=0
use_debug_fission=false
symbol_level=1

clang_use_chrome_plugins=false

clang_version="18"
use_thin_lto=true
is_debug=false
use_custom_libcxx=true
use_unofficial_version_number=false
safe_browsing_use_unrar=false
enable_vr=false
enable_nacl=false
build_dawn_tests=false
enable_reading_list=false
enable_iterator_debugging=false
enable_hangout_services_extension=false
angle_has_histograms=false
angle_build_tests=false
build_angle_perftests=false
treat_warnings_as_errors=false
use_qt=false
is_cfi=false
chrome_pgo_phase=0

use_gio=true
use_pulseaudio=true
link_pulseaudio=true
rtc_use_pipewire=true
icu_use_data_file=true
enable_widevine=true
v8_enable_backtrace=true
use_system_zlib=true
use_system_lcms2=true
use_system_libjpeg=true
use_system_libpng=true
use_system_libtiff=true
use_system_freetype=true
use_system_harfbuzz=true
use_system_libopenjpeg2=true
proprietary_codecs=true
ffmpeg_branding="Chrome"
disable_fieldtrial_testing_config=true
'
