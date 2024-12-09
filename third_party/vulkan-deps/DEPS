# This file is used to manage Vulkan dependencies for several repos. It is
# used by gclient to determine what version of each dependency to check out, and
# where.

# Avoids the need for a custom root variable.
use_relative_paths = True
git_dependencies = 'SYNC'

vars = {
  'chromium_git': 'https://chromium.googlesource.com',

  # Current revision of glslang, the Khronos SPIRV compiler.
  'glslang_revision': 'd59c84d388c805022e2bddea08aa41cbe7e43e55',

  # Current revision of Lunarg VulkanTools
  'lunarg_vulkantools_revision': 'a24a94aa0d1fc4e5556bdf9c6b2afe8eacc55326',

  # Current revision of spirv-cross, the Khronos SPIRV cross compiler.
  'spirv_cross_revision': 'b8fcf307f1f347089e3c46eb4451d27f32ebc8d3',

  # Current revision fo the SPIRV-Headers Vulkan support library.
  'spirv_headers_revision': '1b75a4ae0b4289014b4c369301dc925c366f78a6',

  # Current revision of SPIRV-Tools for Vulkan.
  'spirv_tools_revision': '87fcbaf1bc8346469e178711eff27cfd20aa1960',

  # Current revision of Khronos Vulkan-Headers.
  'vulkan_headers_revision': 'd205aff40b4e15d4c568523ee6a26f85138126d9',

  # Current revision of Khronos Vulkan-Loader.
  'vulkan_loader_revision': '452b3fd7d3a3ba5449ee45f32695f943460d8c61',

  # Current revision of Khronos Vulkan-Tools.
  'vulkan_tools_revision': '494d32f2da0bd8a782d88fdaa98b9e1967148d1b',

  # Current revision of Khronos Vulkan-Utility-Libraries.
  'vulkan_utility_libraries_revision': '9b6e18888be3ac761a3f71594c3949f8dc862ccc',

  # Current revision of Khronos Vulkan-ValidationLayers.
  'vulkan_validation_revision': '1fb93701289aab8fbe04299071804cc4f91af323',
}

deps = {
  'glslang/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/glslang@{glslang_revision}',
  },

  'lunarg-vulkantools/src': {
    'url': '{chromium_git}/external/github.com/LunarG/VulkanTools@{lunarg_vulkantools_revision}',
  },

  'spirv-cross/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/SPIRV-Cross@{spirv_cross_revision}',
  },

  'spirv-headers/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/SPIRV-Headers@{spirv_headers_revision}',
  },

  'spirv-tools/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/SPIRV-Tools@{spirv_tools_revision}',
  },

  'vulkan-headers/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/Vulkan-Headers@{vulkan_headers_revision}',
  },

  'vulkan-loader/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/Vulkan-Loader@{vulkan_loader_revision}',
  },

  'vulkan-tools/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/Vulkan-Tools@{vulkan_tools_revision}',
  },

  'vulkan-utility-libraries/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/Vulkan-Utility-Libraries@{vulkan_utility_libraries_revision}',
  },

  'vulkan-validation-layers/src': {
    'url': '{chromium_git}/external/github.com/KhronosGroup/Vulkan-ValidationLayers@{vulkan_validation_revision}',
  },
}
