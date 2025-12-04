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
     - ``16.9x``
     - ``15.4x``
     - ``13.1x``
     - ``13.1x``
   * - ``/json?size=100``
     - ``68.5x``
     - ``66.9x``
     - ``47.4x``
     - ``37.5x``
   * - ``/json?size=10&t=0.1``
     - ``5.2x``
     - ``4.8x``
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
     - ``1.7 s`` / ``5,882.4 rps`` / ``58,823.5 ips``
     - ``28.8 s`` / ``347.2 rps`` / ``3,472.2 ips``
     - ``16.9x``
   * - 3.12
     - ``1.7 s`` / ``5,882.4 rps`` / ``58,823.5 ips``
     - ``26.1 s`` / ``383.1 rps`` / ``3,831.4 ips``
     - ``15.4x``
   * - 3.13
     - ``1.7 s`` / ``5,882.4 rps`` / ``58,823.5 ips``
     - ``22.2 s`` / ``450.5 rps`` / ``4,504.5 ips``
     - ``13.1x``
   * - 3.14
     - ``1.7 s`` / ``5,882.4 rps`` / ``58,823.5 ips``
     - ``22.2 s`` / ``450.5 rps`` / ``4,504.5 ips``
     - ``13.1x``

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
     - ``3.1 s`` / ``3,225.8 rps`` / ``322,580.6 ips``
     - ``212.2 s`` / ``47.1 rps`` / ``4,712.5 ips``
     - ``68.5x``
   * - 3.12
     - ``3.0 s`` / ``3,333.3 rps`` / ``333,333.3 ips``
     - ``200.7 s`` / ``49.8 rps`` / ``4,982.6 ips``
     - ``66.9x``
   * - 3.13
     - ``3.0 s`` / ``3,333.3 rps`` / ``333,333.3 ips``
     - ``142.0 s`` / ``70.4 rps`` / ``7,042.3 ips``
     - ``47.4x``
   * - 3.14
     - ``3.0 s`` / ``3,333.3 rps`` / ``333,333.3 ips``
     - ``112.4 s`` / ``89.0 rps`` / ``8,896.8 ips``
     - ``37.5x``

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
     - ``10.3 s`` / ``970.9 rps`` / ``9,708.7 ips``
     - ``49.0 s`` / ``204.1 rps`` / ``2,040.8 ips``
     - ``4.8x``
   * - 3.13
     - ``10.2 s`` / ``980.4 rps`` / ``9,803.9 ips``
     - ``22.8 s`` / ``438.6 rps`` / ``4,386.0 ips``
     - ``2.2x``
   * - 3.14
     - ``10.2 s`` / ``980.4 rps`` / ``9,803.9 ips``
     - ``22.7 s`` / ``440.5 rps`` / ``4,405.3 ips``
     - ``2.2x``
