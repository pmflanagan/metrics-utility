# main_indirectmanagednodeaudit Collector - Performance Test Results

## Executive Summary

This report presents performance benchmarks for the `main_indirectmanagednodeaudit` collector
introduced as part of the indirect resource collection work. Two dataset sizes were tested on a
multi-node AAP 2.8 instance. A third (large) tier was not completed due to memory pressure on the
live instance.

**Key findings:**

- The collector does a **full-table scan with no date filter**, unlike all other collectors which
  filter by a time window. Its performance scales with total accumulated rows across the lifetime
  of the deployment.
- At 1K rows: **0.06s, 0.12 MB**
- At 100K rows: **4.49s, 37.88 MB**
- Scaling is approximately linear with row count, consistent with a full-table scan.
- At comparable row volumes, performance is in the same ballpark as `job_host_summary_service`.

---

## Test Environment

- **Instance topology:** `cont_b.yml` via AAPQA-ATF-Test-Suite-Yolo
- **AAP version:** 2.8 dev
- **Deployment type:** Containerized, multi-node
- **Controller nodes:** 2x `m6i.xlarge` (4 vCPU, 16 GB RAM)
- **Database node:** 1x `m6i.xlarge` (4 vCPU, 16 GB RAM), external to controller
- **PostgreSQL:** Parallel workers disabled (`SET max_parallel_workers_per_gather = 0`)
- **Memory tracking:** Enabled via psutil

---

## Dataset Sizes

| Tier | Jobs | Hosts | Job Events | Indirect Node Records |
|------|------|-------|-----------|----------------------|
| Small | 20 | 100 | ~115K | 1,000 |
| Medium | 20 | 1,000 | ~1.27M | 100,000 |
| Large | - | - | - | 1,000,000 |

**Note on indirect node records:** Synthetic records were populated with realistic Ansible
collection module names drawn from collections that have `event_query.yml` files in
`ee-supported-rhel9` (`cisco.intersight`, `microsoft.ad`, `vmware.vmware`). Empty `events`
fields would cause records to appear under `_no_collection` in the anonymized payload.

---

## Small Dataset Results (~115K events, 1K indirect records)

**Test date:** 2026-07-20

### Individual Collector Performance

| Collector | Duration | Memory |
|-----------|----------|--------|
| execution_environments | 0.01s | 0.88 MB |
| unified_jobs | 0.01s | 0.38 MB |
| job_host_summary_service | 0.13s | 4.50 MB |
| main_jobevent_service | 44.28s | 303.80 MB |
| **main_indirectmanagednodeaudit** | **0.06s** | **0.12 MB** |
| **Total** | **44.49s** | **309.68 MB** |

### Full Service Simulation

| Metric | Value |
|--------|-------|
| Total duration | 43.46s (0.72 minutes) |
| Memory before | 116.23 MB |
| Memory after | 309.48 MB |
| Memory consumed | 193.26 MB |

---

## Medium Dataset Results (~1.27M events, 100K indirect records)

**Test date:** 2026-07-20

### Individual Collector Performance

| Collector | Duration | Memory |
|-----------|----------|--------|
| execution_environments | 0.01s | 1.00 MB |
| unified_jobs | 0.02s | 0.62 MB |
| job_host_summary_service | 1.28s | 45.04 MB |
| main_jobevent_service | 95.15s | 561.19 MB |
| **main_indirectmanagednodeaudit** | **4.49s** | **37.88 MB** |
| **Total** | **100.95s** | **645.73 MB** |

### Full Service Simulation

| Metric | Value |
|--------|-------|
| Total duration | 95.86s (1.60 minutes) |
| Memory before | 116.13 MB |
| Memory after | 434.36 MB |
| Memory consumed | 318.23 MB |

---

## Large Dataset (Not Completed)

The 1M indirect record tier was not completed. The instance went unresponsive under memory
pressure from generating ~300M job events alongside 1M indirect records. This tier requires
an isolated database rather than a live AAP instance to run reliably.

---

## Analysis

### Scaling behaviour of main_indirectmanagednodeaudit

| Tier | Indirect Records | Duration | Memory | Duration Ratio | Records Ratio |
|------|-----------------|----------|--------|----------------|---------------|
| Small | 1,000 | 0.06s | 0.12 MB | 1.0x | 1.0x |
| Medium | 100,000 | 4.49s | 37.88 MB | 74.8x | 100x |

The collector scales slightly sub-linearly - 100x more rows produces ~75x more time. This is
consistent with a full-table scan where PostgreSQL buffer cache and query planner optimisations
help at scale.

Memory grows from 0.12 MB to 37.88 MB across the same 100x increase - approximately linear,
which is expected since all rows must be loaded into memory for the rollup computation.

### Comparison with existing collectors at medium scale

| Collector | Duration (Medium) | Memory (Medium) |
|-----------|------------------|-----------------|
| main_jobevent_service | 95.15s | 561.19 MB |
| **main_indirectmanagednodeaudit** | **4.49s** | **37.88 MB** |
| job_host_summary_service | 1.28s | 45.04 MB |

At 100K rows, the indirect node collector is between `job_host_summary_service` and
`main_jobevent_service` in cost. Importantly, the comparison is not apples-to-apples:
`main_jobevent_service` and `job_host_summary_service` filter by a date window (one month
here), while `main_indirectmanagednodeaudit` scans all rows regardless of date. As the
deployment ages and indirect node records accumulate, this collector will grow in cost
while the others remain bounded by the collection window.

### Comparison with reference results

The existing performance document (run against an isolated local database) shows
`job_host_summary_service` completing in 0.08s at ~1.15M events. Our result of 1.28s
at similar scale is ~16x slower, attributable to the external database node being on a
separate host over a network hop and under concurrent load from the live AAP platform.
Results from this report should be treated as representative of a deployed multi-node
environment rather than an isolated baseline.

---

## Recommendations

1. **Monitor table growth.** Because `main_indirectmanagednodeaudit` is a full-table scan,
   its cost will grow unboundedly as the deployment runs more indirect node jobs. Consider
   adding a date filter in a future iteration once the collection window requirements are
   established.

2. **Large-scale testing.** The 1M row tier should be run against an isolated database
   (e.g. via the OpenStack path using `ESTeamYoloPipeline`) to get a production-scale
   data point without risking instance stability.

3. **Real data validation.** Synthetic records use module names from collections with
   `event_query.yml` files but are not generated via real job execution. Real data
   validation requires the `ESTeamYoloPipeline` OpenStack path with VMware infrastructure,
   which is the only currently supported pipeline that produces real
   `main_indirectmanagednodeaudit` records.
