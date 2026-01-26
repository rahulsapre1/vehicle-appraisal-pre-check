-- Add 4-character short IDs for user-facing appraisal references
-- This keeps UUIDs internally for database integrity while showing users friendly 4-char IDs

-- Add short_id column to appraisals table
ALTER TABLE appraisals 
ADD COLUMN IF NOT EXISTS short_id TEXT UNIQUE;

-- Create index for fast lookups by short_id
CREATE INDEX IF NOT EXISTS idx_appraisals_short_id 
ON appraisals(short_id);

-- Function to generate a random 4-character alphanumeric ID
CREATE OR REPLACE FUNCTION generate_short_id()
RETURNS TEXT AS $$
DECLARE
    chars TEXT := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; -- Removed confusing chars: I, O, 0, 1
    result TEXT := '';
    i INTEGER;
    max_attempts INTEGER := 100;
    attempt INTEGER := 0;
    is_unique BOOLEAN := FALSE;
BEGIN
    WHILE NOT is_unique AND attempt < max_attempts LOOP
        result := '';
        FOR i IN 1..4 LOOP
            result := result || substr(chars, floor(random() * length(chars) + 1)::integer, 1);
        END LOOP;
        
        -- Check if this ID already exists
        SELECT NOT EXISTS(SELECT 1 FROM appraisals WHERE short_id = result) INTO is_unique;
        attempt := attempt + 1;
    END LOOP;
    
    IF NOT is_unique THEN
        RAISE EXCEPTION 'Could not generate unique short_id after % attempts', max_attempts;
    END IF;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Generate short_ids for all existing appraisals
DO $$
DECLARE
    appraisal_record RECORD;
BEGIN
    FOR appraisal_record IN 
        SELECT id FROM appraisals WHERE short_id IS NULL
    LOOP
        UPDATE appraisals 
        SET short_id = generate_short_id()
        WHERE id = appraisal_record.id;
    END LOOP;
END $$;

-- Make short_id NOT NULL after populating existing rows
ALTER TABLE appraisals 
ALTER COLUMN short_id SET NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN appraisals.short_id IS 'User-facing 4-character alphanumeric reference ID';
