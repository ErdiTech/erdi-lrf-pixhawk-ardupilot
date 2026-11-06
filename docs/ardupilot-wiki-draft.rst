.. _common-erdi-lrf:

============================
ERDI 905 nm Laser Rangefinders
==============================

.. warning::

   **Draft only — requires real-hardware testing before submission.** This page
   is not an ArduPilot-supported product page until the Lua script, wiring and
   log results have been verified on the target flight controller.

   This draft was prepared by/for **ERDI TECH LTD (the manufacturer)**. The
   manufacturer relationship must be disclosed in any eventual pull request.

The `ERDI 905 nm model catalogue <https://erdilrf.com/models/>`__ contains
rangefinder modules that output a proprietary UART protocol. ArduPilot does
not currently have a native ERDI backend. The draft `erdi_lrf.lua` script uses
the Scripting serial protocol and the Lua rangefinder backend instead.

.. note::

   The B-family (``0x5C`` streaming) path is the first implementation target.
   The A-family (``0x55 0xAA`` command/reply) path is included as an
   experimental single-poll mode; continuous ``0x89`` mode is intentionally
   not used because the A1 source manuals record a request/reply function-byte
   mismatch.

.. image:: ../../../images/erdi-lrf50h.jpg
   :target: ../_images/erdi-lrf50h.jpg
   :width: 300px

Specifications
==============

The links below point to the corresponding ERDI model pages. Confirm the
revision-specific datasheet, supply range and pinout before installation.

.. list-table::
   :header-rows: 1

   * - Model
     - Published range
     - UART output
     - B-frame unit / length
     - Product page
   * - LRF50H
     - 0.05 m to 50 m
     - 460800 baud, 8N1 (adjustable)
     - cm / 4 bytes
     - `LRF50H <https://erdilrf.com/models/lrf50h/>`__
   * - LRF100H
     - 0.05 m to 100 m
     - 460800 baud, 8N1 (adjustable)
     - cm / 4 bytes
     - `LRF100H <https://erdilrf.com/models/lrf100h/>`__
   * - LRF200H
     - 0.05 m to 200 m
     - 460800 baud, 8N1 (adjustable)
     - cm / 4 bytes
     - `LRF200H <https://erdilrf.com/models/lrf200h/>`__
   * - LRF300H
     - 0.05 m to 300 m
     - 460800 baud, 8N1 (adjustable)
     - cm / 4 bytes
     - `LRF300H <https://erdilrf.com/models/lrf300h/>`__
   * - LRF600H
     - 0.05 m to 600 m
     - 460800 baud, 8N1 (adjustable)
     - cm / 4 bytes
     - `LRF600H <https://erdilrf.com/models/lrf600h/>`__
   * - LRF1500H
     - 0.05 m to 1500 m
     - 460800 baud, 8N1 (adjustable)
     - cm / 5 bytes (24-bit)
     - `LRF1500H <https://erdilrf.com/models/lrf1500h/>`__
   * - LRF22VB
     - 0.05 m to 20 m
     - 460800 baud, 8N1 (adjustable)
     - mm / 4 bytes
     - `LRF22VB <https://erdilrf.com/models/lrf22vb/>`__
   * - LRF50VB
     - 0.05 m to 50 m
     - 460800 baud, 8N1 (adjustable)
     - mm / 4 bytes
     - `LRF50VB <https://erdilrf.com/models/lrf50vb/>`__

The H-series manuals reviewed for this draft specify a 9--36 V DC supply;
do **not** power those modules from a flight controller 5 V rail. Confirm the
VB-series supply and signal level from its model manual. The sensor TX connects
to the autopilot RX, sensor RX to autopilot TX, and grounds must be common.

Protocol summary
================

For B-family modules, a frame is ``5C distance_low distance_high checksum``
(or one additional distance byte for LRF1500H). The distance is little-endian.
The checksum is the 8-bit inverse of the sum of the distance bytes. The
out-of-range marker is model-specific (for example ``0xFFFF`` for H series,
``20000`` for LRF22VB and ``50000`` for LRF50VB).

The A-family manuals describe an 8-byte frame
``55 AA function status/reserved distance_high distance_low checksum``. The
single-ranging request is ``55 AA 88 FF FF FF FF 84``; successful replies have
``function=0x88`` and ``status=1`` and report distance in decimetres. Set
``ERDI_MODE=1`` only after confirming the exact A-family model and baud rate.

Lua script installation and parameters
=======================================

These settings assume the sensor is on Serial2. Substitute the actual
``SERIALx_`` port for another connection.

* Set :ref:`SCR_ENABLE<SCR_ENABLE>` = 1 and
  :ref:`SCR_HEAP_SIZE<SCR_HEAP_SIZE>` >= 150000, then reboot.
* Set :ref:`SERIAL2_PROTOCOL<SERIAL2_PROTOCOL>` = 28 (Scripting).
* Set :ref:`RNGFND1_TYPE<RNGFND1_TYPE>` = 36 (Lua Scripting).
* Copy ``erdi_lrf.lua`` to the autopilot SD card ``APM/scripts`` directory and
  reboot. Refresh parameters if the ``ERDI_`` group is not immediately shown.
* Configure the script parameters:

  * ``ERDI_MODE`` = 0 for B-family streaming, 1 for A-family polling.
  * ``ERDI_SP`` = 1 for the first scripting serial port (2 if it is the second).
  * ``ERDI_BR`` = the sensor baud (normally 460800 for B, 115200 for A).
  * ``ERDI_UNIT`` = 0.01 for H-series centimetres, 0.001 for VB millimetres.
  * ``ERDI_LEN`` = 4, or 5 for LRF1500H (ignored in A mode).
  * ``ERDI_OOR`` = the model's documented raw out-of-range marker.
  * ``ERDI_POLL_MS`` = 200 or slower for A mode (ignored in B mode).

Set :ref:`RNGFND1_MAX <RNGFND1_MAX>` and
:ref:`RNGFND1_MIN <RNGFND1_MIN>` to the model's metres range, and set
:ref:`RNGFND1_ORIENT<RNGFND1_ORIENT>` to the mounting orientation (25 is
downward). The script reports a valid distance through
``AP_RangeFinder_Backend_ud:handle_script_msg``.

Testing
=======

Run SITL and the protocol unit tests before connecting a powered module. On a
real vehicle, inspect the Mission Planner Flight Data **Status** tab for
``rangefinder1`` and review the ``RFND`` data-flash message for valid distance,
minimum/maximum limits and timeout behaviour. Follow
``HARDWARE-TEST-CHECKLIST.md`` in this package and retain the log and wiring
photos for any upstream submission.

Implementation references
=========================

The Lua API and style were checked against ArduPilot master on 2026-11-02:

* ``ardupilot/libraries/AP_Scripting/drivers/TOFSense-M/TOFSense-M_Serial.lua``
* ``ardupilot/libraries/AP_Scripting/docs/docs.lua``
* ``ardupilot/libraries/AP_Scripting/generator/description/bindings.desc``
* ``ardupilot/libraries/AP_Scripting/examples/rangefinder_quality_test.lua``
* ``ardupilot_wiki/common/source/docs/common-corvon-cv08-cv50.rst``

The protocol details used for this draft come from the manufacturer manuals of
the LRF50H, LRF1500H, LRF22VB, LRF50VB, LRF1200A1 and LRF3000A1.

.. note::

   This page must not be submitted until a real flight-controller test proves
   UART stability, checksum handling, correct units, timeout behaviour and
   ``RFND`` logging for at least one representative H or VB model.
