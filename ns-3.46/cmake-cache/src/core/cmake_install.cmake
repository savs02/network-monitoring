# Install script for directory: /Users/savanisawaikar/network-monitoring/ns-3.46/src/core

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
  include("/Users/savanisawaikar/network-monitoring/ns-3.46/cmake-cache/src/core/examples/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE SHARED_LIBRARY FILES "/Users/savanisawaikar/network-monitoring/ns-3.46/build/lib/libns3.46-core-default.dylib")
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-core-default.dylib" AND
     NOT IS_SYMLINK "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-core-default.dylib")
    execute_process(COMMAND /usr/bin/install_name_tool
      -add_rpath "/usr/local/lib:$ORIGIN/:$ORIGIN/../lib:/usr/local/lib64:$ORIGIN/:$ORIGIN/../lib64"
      "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-core-default.dylib")
    if(CMAKE_INSTALL_DO_STRIP)
      execute_process(COMMAND "/usr/bin/strip" -x "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/libns3.46-core-default.dylib")
    endif()
  endif()
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/ns3" TYPE FILE FILES
    "/Users/savanisawaikar/network-monitoring/ns-3.46/build/include/ns3/core-config.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/int64x64-128.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/example-as-test.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/helper/csv-reader.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/helper/event-garbage-collector.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/helper/random-variable-stream-helper.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/abort.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/ascii-file.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/ascii-test.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/assert.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/attribute-accessor-helper.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/attribute-construction-list.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/attribute-container.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/attribute-helper.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/attribute.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/boolean.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/breakpoint.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/build-profile.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/calendar-scheduler.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/callback.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/command-line.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/config.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/default-deleter.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/default-simulator-impl.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/demangle.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/deprecated.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/des-metrics.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/double.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/enum.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/event-id.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/event-impl.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/fatal-error.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/fatal-impl.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/fd-reader.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/environment-variable.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/global-value.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/hash-fnv.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/hash-function.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/hash-murmur3.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/hash.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/heap-scheduler.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/int64x64-double.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/int64x64.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/integer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/length.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/list-scheduler.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/log-macros-disabled.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/log-macros-enabled.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/log.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/make-event.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/map-scheduler.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/math.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/names.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/node-printer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/nstime.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/object-base.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/object-factory.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/object-map.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/object-ptr-container.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/object-vector.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/object.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/pair.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/pointer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/priority-queue-scheduler.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/ptr.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/random-variable-stream.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/rng-seed-manager.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/rng-stream.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/scheduler.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/show-progress.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/shuffle.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/simple-ref-count.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/simulation-singleton.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/simulator-impl.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/simulator.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/singleton.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/string.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/synchronizer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/system-path.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/system-wall-clock-ms.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/system-wall-clock-timestamp.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/test.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/time-printer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/timer-impl.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/timer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/trace-source-accessor.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/traced-callback.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/traced-value.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/trickle-timer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/tuple.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/type-id.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/type-name.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/type-traits.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/uinteger.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/uniform-random-bit-generator.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/valgrind.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/vector.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/warnings.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/watchdog.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/realtime-simulator-impl.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/wall-clock-synchronizer.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/val-array.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/src/core/model/matrix-array.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/build/include/ns3/core-module.h"
    "/Users/savanisawaikar/network-monitoring/ns-3.46/build/include/ns3/core-export.h"
    )
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "/Users/savanisawaikar/network-monitoring/ns-3.46/cmake-cache/src/core/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
