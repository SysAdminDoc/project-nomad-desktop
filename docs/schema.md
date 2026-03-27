# N.O.M.A.D. Database Schema

SQLite database (`nomad.db`) managed by `db.py`.

---

## Internal / System

| Table | Purpose |
|---|---|
| `_migrations` | Tracks applied SQL migration files (filename, applied_at) |
| `services` | Registered micro-services (installed, running, port, pid) |
| `settings` | Key-value application settings |
| `activity_log` | Timestamped event log (event, service, detail, level) |
| `sync_log` | Federation push/pull sync history |
| `vector_clocks` | CRDT vector clocks for conflict detection during federation sync |

## Notes & Knowledge

| Table | Purpose |
|---|---|
| `notes` | User notes with title, content, tags, pinned flag |
| `note_tags` | Many-to-many tag assignments for notes |
| `note_links` | Bi-directional links between notes |
| `note_templates` | Reusable note templates |
| `conversations` | AI chat conversations (messages stored as JSON) |
| `conversation_branches` | Branched conversation threads |
| `documents` | Uploaded/indexed documents for RAG |
| `kb_workspaces` | Knowledge-base workspaces grouping documents |
| `journal` | Daily journal entries with mood/tags |

## Inventory & Supplies

| Table | Purpose |
|---|---|
| `inventory` | General supply inventory (quantity, expiration, barcode, cost) |
| `inventory_photos` | Photos attached to inventory items |
| `inventory_checkouts` | Checkout/return tracking for inventory items |
| `shopping_list` | Items needed, optionally linked to inventory |
| `ammo_inventory` | Ammunition inventory by caliber |
| `fuel_storage` | Fuel reserves (type, quantity, stabilizer, expiry) |
| `upc_database` | Barcode lookup database seeded with common prep items |

## Medical

| Table | Purpose |
|---|---|
| `patients` | Patient records (linked to contacts, triage category) |
| `vitals_log` | Vital-sign readings per patient (BP, pulse, SpO2, GCS) |
| `wound_log` | Wound tracking per patient |
| `wound_photos` | Photos attached to wound records |
| `drug_interactions` | Drug-drug interaction reference data |
| `triage_events` | Mass-casualty triage event headers |
| `handoff_reports` | SBAR patient handoff reports |

### Relationships
- `vitals_log.patient_id` -> `patients.id`
- `wound_log.patient_id` -> `patients.id`
- `wound_photos.wound_id` -> `wound_log.id`
- `handoff_reports.patient_id` -> `patients.id`
- `patients.contact_id` -> `contacts.id`

## Garden & Agriculture

| Table | Purpose |
|---|---|
| `garden_plots` | Garden plot definitions (size, sun, soil, geo) |
| `seeds` | Legacy seed stock |
| `seed_inventory` | Detailed seed inventory (viability, spacing, depth) |
| `harvest_log` | Harvest records by crop and plot |
| `planting_calendar` | Zone-based monthly planting schedule |
| `preservation_log` | Food preservation batches (canning, drying, etc.) |
| `companion_plants` | Companion/antagonist plant relationships |
| `pest_guide` | Pest identification and treatment reference |
| `livestock` | Animal records (species, tag, health, vaccinations) |

### Relationships
- `harvest_log.plot_id` -> `garden_plots.id`

## Weather & Sensors

| Table | Purpose |
|---|---|
| `weather_log` | Manual/imported weather observations |
| `weather_readings` | Structured weather readings with Zambretti predictions |
| `weather_action_rules` | Automated alert rules triggered by weather conditions |
| `sensor_devices` | Registered sensor hardware |
| `sensor_readings` | Time-series sensor data points |

### Relationships
- `sensor_readings.device_id` -> `sensor_devices.id`

## Communications

| Table | Purpose |
|---|---|
| `contacts` | People directory (callsign, role, freq, medical info) |
| `comms_log` | Radio communication log entries |
| `freq_database` | Frequency allocation reference database |
| `radio_profiles` | Saved radio channel programming profiles |
| `lan_messages` | Local-network chat messages |
| `lan_channels` | Chat channel definitions |
| `lan_presence` | LAN node presence/heartbeat |
| `lan_transfers` | File transfer tracking |
| `mesh_messages` | Meshtastic mesh-network messages |

## Security & Perimeter

| Table | Purpose |
|---|---|
| `cameras` | Surveillance camera definitions (URL, stream type) |
| `access_log` | Physical entry/exit log |
| `perimeter_zones` | Geofenced security zones |
| `alerts` | System and security alerts |
| `vault_entries` | Encrypted credential/secret storage |
| `incidents` | Incident reports (severity, category) |

## Power & Equipment

| Table | Purpose |
|---|---|
| `power_devices` | Solar panels, batteries, generators |
| `power_log` | Power production/consumption readings |
| `equipment_log` | Equipment maintenance and service tracking |

## Federation (Multi-Node)

| Table | Purpose |
|---|---|
| `federation_peers` | Known peer nodes (trust level, geo, public key) |
| `federation_offers` | Items offered to the network |
| `federation_requests` | Items requested from the network |
| `federation_sitboard` | Shared situational awareness board |
| `mutual_aid_agreements` | Formal mutual-aid contracts between nodes |
| `dead_drop_messages` | Encrypted asynchronous node-to-node messages |
| `group_exercises` | Multi-node training exercises |

## Training & AI

| Table | Purpose |
|---|---|
| `training_datasets` | Fine-tuning dataset metadata |
| `training_jobs` | Fine-tuning job tracking |
| `scenarios` | Solo training scenario runs |
| `drill_history` | Completed drill records |
| `skills` | Personal skill tracking and proficiency |

### Relationships
- `training_jobs.dataset_id` -> `training_datasets.id`

## Media & Library

| Table | Purpose |
|---|---|
| `videos` | Video library catalog |
| `audio` | Audio/music library catalog |
| `books` | E-book library catalog |
| `media_progress` | Playback position tracking (any media type) |
| `playlists` | Audio/video playlists |
| `subscriptions` | RSS/feed channel subscriptions |

## Scheduling & Tasks

| Table | Purpose |
|---|---|
| `checklists` | Reusable checklists with templates |
| `timers` | Countdown timers |
| `scheduled_tasks` | Recurring task scheduler |
| `watch_schedules` | Shift/watch rotation planner |

## Maps & Navigation

| Table | Purpose |
|---|---|
| `waypoints` | GPS waypoints with category, icon, elevation |
| `map_routes` | Multi-waypoint routes with GPX data |
| `map_annotations` | GeoJSON map overlays |

## Other

| Table | Purpose |
|---|---|
| `benchmarks` | System benchmark results (legacy) |
| `benchmark_results` | Extended benchmark results (v5.0) |
| `community_resources` | Nearby community asset directory |
| `radiation_log` | Radiation dose-rate readings |

---

## Migration System

Migrations live in `db_migrations/` as numbered SQL files (e.g., `001_add_migrations_table.sql`).
On every `init_db()` call, unapplied migrations are executed in filename order and recorded in `_migrations`.
Each migration runs inside a transaction; a failure rolls back that single migration and raises an error.
