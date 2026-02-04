# Install script for directory: /Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "default")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/Users/savanisawaikar/network-monitoring/ns-3.46/cmake-cache/src/buildings/examples/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/Users/savanisawaikar/network-monitoring/ns-3.46/build/lib/libns3.46-buildings-default.dylib")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-buildings-default.dylib" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-buildings-default.dylib")
    execute_process(COMMAND /usr/bin/install_name_tool
      -delete_rpath "/Users/savanisawaikar/network-monitoring/ns-3.46/build/lib"
      -add_rpath "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64"
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-buildings-default.dylib")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" -x "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-buildings-default.dylib")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/helper/building-allocator.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/helper/building-container.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/helper/building-position-allocator.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/helper/buildings-helper.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/building-list.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/building.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/buildings-channel-condition-model.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/buildings-propagation-loss-model.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/hybrid-buildings-propagation-loss-model.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/itu-r-1238-propagation-loss-model.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/mobility-building-info.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/oh-buildings-propagation-loss-model.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/random-walk-2d-outdoor-mobility-model.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/buildings/model/three-gpp-v2v-channel-condition-model.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/build/include/ns3/buildings-module.h"
    )
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/Users/savanisawaikar/network-monitoring/ns-3.46/cmake-cache/src/buildings/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
