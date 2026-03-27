# Project N.O.M.A.D. v5.0 Roadmap

> Feature expansion roadmap based on competitive analysis of 40+ open source projects.
> Each phase is independently shippable. Phases are ordered by impact and dependency.
>
> **Status key:** ✅ Done | ◐ Partial | ⬚ Not started

---

## Phase 1: AI Chat Enhancements
**Inspiration:** GPT4All (LocalDocs), Jan.ai (model marketplace), Open WebUI (branching)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Folder-based document ingestion | Watch a folder, auto-index new files into KB — like GPT4All's LocalDocs | Medium | ✅ API + KB workspaces |
| Model cards in picker | Show param count, quant level, RAM needed, speed benchmark per model | Low | ✅ `/api/ai/model-info` + UI |
| Conversation branching | Fork from any message to explore alternative responses | Medium | ✅ Fork button + branch API |
| Workspace-scoped RAG | Create named knowledge bases ("Medical KB", "Water KB") instead of one global KB | Medium | ✅ KB workspaces CRUD |
| Image input (multimodal) | Support vision models (llava, etc.) — paste/upload images into chat | Medium | ✅ Camera button + multimodal API |

---

## Phase 2: Knowledge Base Upgrade
**Inspiration:** RAGFlow (GraphRAG), LlamaIndex (hierarchical chunks), LanceDB (embedded)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Replace Qdrant with LanceDB | Embedded vector DB — no separate server process, smaller footprint | Medium | ⬚ Architectural — deferred |
| Hybrid retrieval | Combine vector search + BM25 keyword search for better accuracy | Medium | ⬚ Deferred |
| Hierarchical chunking | Parent/child document structures that preserve section context | Medium | ⬚ Deferred |
| Source citations | AI answers include page numbers and document names as clickable references | Low | ✅ `formatSourceCitations()` + KB badge |
| Auto-OCR pipeline | PDFs auto-OCR'd on upload via Stirling-PDF, then indexed into KB | Low | ✅ Upload OCR + folder watch pipeline |

---

## Phase 3: Inventory Upgrades
**Inspiration:** InvenTree (barcode scanning), OpenBoxes (lot tracking), Snipe-IT (check-out)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Barcode/QR scanning | Webcam-based barcode scanner for quick item lookup and add | Low | ✅ `/api/inventory/scan` |
| Photo attachments | Camera capture attached to inventory items | Low | ✅ Upload API + UI |
| Check-in/check-out | Track who has which equipment ("who has the generator?") | Medium | ✅ Checkout/checkin API + badge |
| Lot tracking | Track batch numbers for medical supplies, water tablets, ammo lots | Medium | ✅ `lot_number` column + form |
| Location tracking | Which cache, building, or vehicle holds each supply | Low | ✅ Location field + filter |
| Auto-shopping list | Generate shopping list from items below minimum threshold | Low | ✅ `/api/inventory/shopping-list` |

---

## Phase 4: Maps & Navigation
**Inspiration:** Protomaps (style themes), OSRM (offline routing), GPX standard

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Multiple map styles | Dark tactical, terrain/topo, satellite, minimal — switch via button | Low | ✅ 3 styles, cycle button |
| Offline routing | OSRM or Valhalla for driving/walking route calculation without internet | High | ⬚ Requires large data — deferred |
| GPX import/export | Load GPS tracks onto the map, export waypoint routes as GPX | Medium | ✅ Import + export |
| Distance/area measurement | Click-to-measure tool on map | Low | ✅ Haversine measurement tool |
| Print map to PDF | Print current map view at specified scale for field use | Medium | ✅ Canvas export + print |
| Elevation profiles | Show elevation graph along a route or between waypoints | Medium | ✅ Canvas chart + Saved Routes panel |

---

## Phase 5: Notes Overhaul
**Inspiration:** Obsidian (wiki-links, graph), Joplin (tags, encryption), Logseq (daily journal)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Wiki-links `[[page]]` | Type `[[` to autocomplete link to another note; clickable bidirectional links | Medium | ✅ Rendering + `openWikiLink()` |
| Tags | `#medical #water #urgent` with tag-based filtering sidebar | Low | ✅ Tags CRUD + filter |
| Daily journal mode | One-click "today's log" that auto-timestamps entries | Low | ✅ `/api/notes/journal` |
| Note templates | "Incident Report", "Patrol Log", "Comms Log", "SITREP" etc. | Low | ✅ 6 templates + picker dropdown |
| Note attachments | Embed images, PDFs, audio recordings into notes | Medium | ✅ Upload/serve API + UI |
| Backlink panel | Show all notes that link to the current note | Low | ✅ `loadNoteBacklinks()` |

---

## Phase 6: Media Library
**Inspiration:** Jellyfin (metadata, resume), Audiobookshelf (chapters, bookmarks)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Resume playback | Remember position in videos and audiobooks across sessions | Low | ✅ `media_progress` table + UI |
| Chapter navigation | Jump between chapters in audiobooks and long videos | Medium | ✅ Auto-generated chapters + seek |
| Auto-thumbnail generation | Extract thumbnail frames from video files | Low | ✅ FFmpeg extraction API |
| Playlist creation | Create and manage audio playlists | Low | ✅ Playlists CRUD |
| Subtitle/SRT support | Load subtitle files for video playback | Medium | ✅ Auto-detect `.vtt`/`.srt` + track |
| Metadata editor | Edit title, author, description, tags for media files | Low | ✅ `PUT /api/media/<type>/<id>/metadata` |

---

## Phase 7: Medical Module
**Inspiration:** OpenBoxes (pharma tracking), WHO guidelines, TCCC protocols

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Drug interaction checker | Flag conflicts between medications a patient is taking | Medium | ✅ 26-pair checker |
| Wound documentation with photos | Camera capture attached to patient wound records | Low | ✅ Photo input in wound form |
| Interactive TCCC flowchart | Step-by-step decision tree for tactical casualty care | Medium | ✅ 5-step MARCH flowchart |
| Vital signs trending | Chart BP/HR/temp/SpO2 over time to spot deterioration | Low | ✅ Canvas multi-line chart |
| Medication expiry cross-reference | Link med inventory expiry dates to patient prescriptions | Low | ✅ `/api/medical/expiring-meds` |
| Offline medical reference DB | Curated WHO/public domain guidelines searchable offline | High | ✅ 15 categories + full-text search API |

---

## Phase 8: Radio & Communications
**Inspiration:** CHIRP (freq database), Fldigi (digital modes), Meshtastic (mesh networking)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Expanded frequency database | 22,000+ allocations by region (import from CHIRP data) | Medium | ✅ ~340 frequencies (US/EU/intl bands) |
| Antenna calculator with diagrams | Visual dipole, vertical, Yagi length calculator with SVG diagrams | Low | ✅ 4 antenna types |
| Propagation prediction | Basic HF propagation forecast from time/date/solar conditions | Medium | ✅ MUF estimation + 7-band table |
| Native Meshtastic integration | Connect to Meshtastic via USB serial — send/receive messages from NOMAD | High | ◐ Stub + mesh map overlay |
| DTMF tone generator | Generate DTMF tones for radio programming through audio output | Low | ✅ WebAudio 16-key pad |
| Phonetic alphabet trainer | Interactive practice tool for NATO alphabet | Low | ✅ Quiz mode + reference grid |

---

## Phase 9: Weather & Environment
**Inspiration:** WeeWX (station integration), Open-Meteo, Zambretti algorithm

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Barometric pressure history graph | Track pressure over 24-48hrs with visual trend line | Low | ✅ Canvas chart |
| Zambretti weather prediction | Pure offline forecasting from pressure + wind + season (no internet) | Low | ✅ Full algorithm |
| USB weather station support | Read data from USB weather stations via serial interface | Medium | ⬚ Hardware-dependent — deferred |
| Weather-triggered alerts | Auto-create alerts when pressure drops rapidly or temp hits extremes | Low | ✅ Pressure + temp alerts |
| Wind chill / heat index calculator | Real-time comfort index from temp + wind/humidity | Low | ✅ `/api/weather/wind-chill` |

---

## Phase 10: LAN & Mesh Networking
**Inspiration:** LAN Messenger (file transfer), KouChat (serverless), BeeBEEP (groups)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| LAN file transfer | Drag-and-drop send files between NOMAD instances | Medium | ✅ Send/receive/list APIs |
| Group channels | Named channels ("Security", "Medical", "Logistics") | Low | ✅ Auto-seeded 4 channels |
| Message encryption | AES encrypt LAN chat messages end-to-end | Medium | ✅ AES-GCM via Web Crypto |
| User presence/status | Show online/away/busy for each LAN node | Low | ✅ Heartbeat + presence pills |
| Mesh node map overlay | Show Meshtastic nodes on map with signal strength indicators | Low | ✅ Green dot markers on map |
| Mesh alert relay | Broadcast emergency alerts to all mesh nodes | Low | ✅ Federation relay existing |

---

## Phase 11: Garden & Food Production
**Inspiration:** Plant-it (care tracking), GrowVeg (planting calendar)

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Planting calendar | Auto-calculate plant/harvest dates from last frost date and zone | Low | ✅ Zone-based calendar API |
| Companion planting guide | Reference showing which plants grow well together | Low | ✅ 20 pairs, searchable |
| Harvest yield tracking | Log actual vs expected yield to improve next season | Low | ✅ Existing harvest_log table |
| Seed inventory | Track seed stock with viability dates and germination rates | Low | ✅ `seed_inventory` table + CRUD |
| Pest/disease identifier | Reference guide for common garden problems with treatments | Low | ✅ 10 entries, auto-seeded |

---

## Phase 12: Benchmark & Diagnostics
**Inspiration:** Phoronix Test Suite, sysbench

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| AI inference benchmark | Measure tokens/second per installed model (NOMAD-specific) | Low | ✅ Tokens/sec per model |
| Storage I/O benchmark | Test USB drive speed — critical for offline content performance | Low | ✅ 32MB read/write test |
| Network throughput test | Measure LAN speed for multi-node setups | Low | ✅ TCP socket benchmark |
| Historical comparison graph | Chart benchmark scores over time to detect degradation | Low | ✅ Extended results table |

---

## Completion Summary

| Phase | Done | Total | Pct |
|-------|------|-------|-----|
| 1. AI Chat | 5 | 5 | 100% |
| 2. KB Upgrade | 2 | 5 | 40% |
| 3. Inventory | 6 | 6 | 100% |
| 4. Maps | 5 | 6 | 83% |
| 5. Notes | 6 | 6 | 100% |
| 6. Media | 6 | 6 | 100% |
| 7. Medical | 6 | 6 | 100% |
| 8. Radio | 5 | 6 | 83% |
| 9. Weather | 4 | 5 | 80% |
| 10. LAN/Mesh | 6 | 6 | 100% |
| 11. Garden | 5 | 5 | 100% |
| 12. Benchmark | 4 | 4 | 100% |
| **Total** | **60** | **66** | **91%** |

### Deferred Items (6 remaining)
- Phase 2: LanceDB migration, hybrid search, hierarchical chunking (architectural — requires Qdrant replacement)
- Phase 4: Offline routing (requires OSRM/Valhalla + ~200MB routing data per region)
- Phase 8: Full Meshtastic serial integration (hardware-dependent, stub exists)
- Phase 9: USB weather station (hardware-dependent)

### Automated Test Suite
- 287 pytest tests across 29 files covering all major API surfaces
- Tests: inventory, notes, contacts, conversations, weather, medical, checklists, core, radio, maps, garden, supplies, benchmark, KB, medical reference, skills, community, radiation, OCR pipeline, validation, incidents, tasks, vault, livestock, scenarios, timers, power, cameras, data-summary/global-search
