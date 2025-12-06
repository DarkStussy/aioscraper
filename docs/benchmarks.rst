Benchmarks
==========

Local JSON server comparisons against ``scrapy`` (10,000 requests per run).
The scripts used for these tests are available in
`this Gist <https://gist.github.com/DarkStussy/dc5d3c2b4029428e990ad44190f4cdbc>`_;
results below are frozen from those runs. Both frameworks ran with ``uvloop``
instead of the default event loop.

Overall, ``aioscraper`` throughput stays flat across CPython 3.11–3.14, while
``scrapy`` speeds up on newer interpreters but remains far slower once payload
size grows.


.. list-table::
   :header-rows: 1
   :widths: 26 18 18 18 18
   :class: benchmarks-table

   * - Endpoint
     - 3.11
     - 3.12
     - 3.13
     - 3.14
   * - ``/json?size=10``
     - ``13.7x``
     - ``12.4x``
     - ``10.6x``
     - ``10.6x``
   * - ``/json?size=100``
     - ``60.7x``
     - ``59.1x``
     - ``41.8x``
     - ``34.1x``
   * - ``/json?size=10&t=0.1``
     - ``5.2x``
     - ``4.7x``
     - ``2.2x``
     - ``2.2x``

Endpoint breakdown
------------------

Legend: columns show ``elapsed`` (seconds), ``rps`` (requests/sec), and ``ips`` (items/sec) for each library.

``/json?size=10``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*10,000 requests / 100,000 items*

.. list-table::
   :header-rows: 1
   :widths: 8 32 32 8
   :class: benchmarks-table

   * - Python
     - aioscraper
     - scrapy
     - Gap
   * - 3.11
     - ``2.1 s`` / ``4,761.9 rps`` / ``47,619.0 ips``
     - ``28.8 s`` / ``347.2 rps`` / ``3,472.2 ips``
     - ``13.7x``
   * - 3.12
     - ``2.1 s`` / ``4,761.9 rps`` / ``47,619.0 ips``
     - ``26.1 s`` / ``383.1 rps`` / ``3,831.4 ips``
     - ``12.4x``
   * - 3.13
     - ``2.1 s`` / ``4,761.9 rps`` / ``47,619.0 ips``
     - ``22.2 s`` / ``450.5 rps`` / ``4,504.5 ips``
     - ``10.6x``
   * - 3.14
     - ``2.1 s`` / ``4,761.9 rps`` / ``47,619.0 ips``
     - ``22.2 s`` / ``450.5 rps`` / ``4,504.5 ips``
     - ``10.6x``

``/json?size=100``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*10,000 requests / 1,000,000 items*

.. list-table::
   :header-rows: 1
   :widths: 8 32 32 8
   :class: benchmarks-table

   * - Python
     - aioscraper
     - scrapy
     - Gap
   * - 3.11
     - ``3.5 s`` / ``2,857.1 rps`` / ``285,714.3 ips``
     - ``212.2 s`` / ``47.1 rps`` / ``4,712.5 ips``
     - ``60.7x``
   * - 3.12
     - ``3.4 s`` / ``2,941.2 rps`` / ``294,117.6 ips``
     - ``200.7 s`` / ``49.8 rps`` / ``4,982.6 ips``
     - ``59.1x``
   * - 3.13
     - ``3.4 s`` / ``2,941.2 rps`` / ``294,117.6 ips``
     - ``142.0 s`` / ``70.4 rps`` / ``7,042.3 ips``
     - ``41.8x``
   * - 3.14
     - ``3.3 s`` / ``3,030.3 rps`` / ``303,030.3 ips``
     - ``112.4 s`` / ``89.0 rps`` / ``8,896.8 ips``
     - ``34.1x``

``/json?size=10&t=0.1``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
*10,000 requests / 100,000 items, +100 ms delay*

.. list-table::
   :header-rows: 1
   :widths: 8 32 32 8
   :class: benchmarks-table

   * - Python
     - aioscraper
     - scrapy
     - Gap
   * - 3.11
     - ``10.4 s`` / ``961.5 rps`` / ``9,615.4 ips``
     - ``54.1 s`` / ``184.8 rps`` / ``1,848.4 ips``
     - ``5.2x``
   * - 3.12
     - ``10.4 s`` / ``961.5 rps`` / ``9,615.4 ips``
     - ``49.0 s`` / ``204.1 rps`` / ``2,040.8 ips``
     - ``4.7x``
   * - 3.13
     - ``10.4 s`` / ``961.5 rps`` / ``9,615.4 ips``
     - ``22.8 s`` / ``438.6 rps`` / ``4,386.0 ips``
     - ``2.2x``
   * - 3.14
     - ``10.3 s`` / ``970.9 rps`` / ``9,708.7 ips``
     - ``22.7 s`` / ``440.5 rps`` / ``4,405.3 ips``
     - ``2.2x``
