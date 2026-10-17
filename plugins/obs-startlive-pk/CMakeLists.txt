cmake_minimum_required(VERSION 3.28)
project(obs-startlive-pk VERSION 0.2.0 LANGUAGES CXX)

find_package(Threads REQUIRED)
# Older Linux libc versions provide shm_open in librt; macOS has it in libc.
if(UNIX AND NOT APPLE)
  link_libraries(rt)
endif()
option(STARTLIVE_PK_BUILD_PLUGIN "Build the OBS plugin (requires the OBS SDK)" ON)
if(STARTLIVE_PK_BUILD_PLUGIN)
  # The Python encoder configuration owns the capture/send FPS ceiling too.
  set(pk_video_config "${CMAKE_CURRENT_SOURCE_DIR}/../../startlive/core/pk/states/encoder.py")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${pk_video_config}")
  file(STRINGS "${pk_video_config}" pk_max_fps_line REGEX "^    frame_rate: int = [0-9]+")
  if(NOT pk_max_fps_line)
    message(FATAL_ERROR "VideoEncodingConfig.frame_rate is missing from ${pk_video_config}")
  endif()
  string(REGEX REPLACE "^    frame_rate: int = ([0-9]+).*" "\\1" pk_max_fps "${pk_max_fps_line}")
  find_package(libobs CONFIG REQUIRED)
  find_package(obs-frontend-api CONFIG REQUIRED)
  find_package(Qt6 REQUIRED COMPONENTS Widgets)
  # OBS 31's Qt helper adds this fallback even when AGL is absent from the SDK.
  # macOS 26 removed AGL; keep OpenGL and all other transitive dependencies.
  if(APPLE AND TARGET WrapOpenGL::WrapOpenGL AND NOT WrapOpenGL_AGL)
    get_target_property(pk_opengl_libraries WrapOpenGL::WrapOpenGL INTERFACE_LINK_LIBRARIES)
    list(REMOVE_ITEM pk_opengl_libraries "-framework AGL")
    set_property(TARGET WrapOpenGL::WrapOpenGL PROPERTY INTERFACE_LINK_LIBRARIES "${pk_opengl_libraries}")
  endif()
  add_library(obs-startlive-pk MODULE src/plugin.cpp src/media_transport.cpp src/shared_video.cpp)
  target_compile_features(obs-startlive-pk PRIVATE cxx_std_17)
  target_compile_definitions(obs-startlive-pk PRIVATE STARTLIVE_PK_MAX_FPS=${pk_max_fps})
  target_link_libraries(obs-startlive-pk PRIVATE OBS::libobs OBS::obs-frontend-api Threads::Threads Qt6::Widgets)
  if(MSVC)
    target_compile_options(obs-startlive-pk PRIVATE /utf-8)
  endif()
  if(WIN32)
    target_compile_definitions(obs-startlive-pk PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
    target_link_libraries(obs-startlive-pk PRIVATE advapi32)
  endif()
  set_target_properties(obs-startlive-pk PROPERTIES PREFIX "")
  if(APPLE)
    set_target_properties(obs-startlive-pk PROPERTIES BUNDLE TRUE BUNDLE_EXTENSION plugin SUFFIX ""
      XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "org.startlive.obs-pk"
      # Resolve OBS/Qt frameworks inside the host OBS.app after installation.
      INSTALL_RPATH "@executable_path/../Frameworks"
      MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/src/Info.plist.in")
    # MODULE bundles use the LIBRARY artifact kind; BUNDLE is for .app executables.
    install(TARGETS obs-startlive-pk LIBRARY DESTINATION .)
  elseif(WIN32)
    install(TARGETS obs-startlive-pk RUNTIME DESTINATION obs-plugins/64bit
            LIBRARY DESTINATION obs-plugins/64bit)
  else()
    include(GNUInstallDirs)
    install(TARGETS obs-startlive-pk LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}/obs-plugins)
  endif()
endif()
