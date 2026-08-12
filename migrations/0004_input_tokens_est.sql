-- Tool call arguments were never counted toward "what's filling up context" (only tool
-- *output* was, via parts.output_tokens_est) - additive column, backfilled on next reindex.
ALTER TABLE parts ADD COLUMN input_tokens_est INTEGER;
