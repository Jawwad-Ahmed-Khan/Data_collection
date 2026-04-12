# Gemini Flash Implementation Plan Summary

## Background
The user requested the integration of a free API to automatically populate infrastructure data (hospitals, schools, bridges, airports, dams) for three key monitoring, locations: **Lahore**, **Karachi**, and **Islamabad**. 

In response, Gemini Flash formulated an **Implementation Plan** to integrate the **OpenStreetMap (OSM) Overpass API**, which is open-source, completely free, and provides rich geospatial data.

## Key Components of the Plan

The implementation plan is structured around three main phases to ensure data is fetched reliably and without duplicating records in the database:

### 1. Schema Enhancement (Idempotency)
The `pakistan_infrastructure` table currently relies on randomly generated UUIDs. If an API pulls down the same 100 hospitals every week, the table would duplicate them infinitely.
* **The Fix**: The plan proposes running an `ALTER TABLE` to add an `external_id` column (storing the unique OSM node/way IDs) with a `UNIQUE` constraint. This enables **UPSERTs**, allowing the system to update existing infrastructure or insert new ones seamlessly without duplication.

### 2. Service & Collector Architecture
To fit gracefully into the ClimaSync structure, the plan introduces two new Python modules:
* **`OSMService` (`app/services/osm_service.py`)**: Responsible for writing the Overpass QL queries (e.g., bounding boxes or radius queries around our cities), parsing the returned GeoJSON, and mapping OSM tags to the system's `asset_type` enum (e.g., translating `amenity=hospital` to `hospital`).
* **`OSMCollector` (`app/collectors/osm_collector.py`)**: Responsible for managing the rate limits and dispatching HTTP requests to the Overpass API for each of the active `pakistan_locations`.

### 3. Execution Strategy (Sync Script)
Because infrastructure data (like a new bridge or hospital) rarely changes on an hourly basis like weather does, wiring it into the 15-minute operational loop is inefficient. 
* **The Solution**: The plan proposes building a dedicated `sync_infrastructure.py` script. This serves as a standalone tool that can be triggered manually or run via a weekly cron job to continuously synchronize the database with the real world.

## Current Status
The plan is currently in the **"Awaiting User Approval"** stage. Once the user approves the approach—specifically the database schema modification—execution will begin to fully automate infrastructure syncing.
