-- Human-editable labels. Both are optional overlays on top of
-- plugin-derived/computed data - never overwritten by ingest or reindex.

ALTER TABLE sources ADD COLUMN display_name TEXT;
ALTER TABLE sessions ADD COLUMN notes TEXT;
