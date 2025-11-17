-- Create models table for managing TikTok model accounts
CREATE TABLE IF NOT EXISTS models (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),

    -- Indexes for faster queries
    CONSTRAINT models_name_not_empty CHECK (model_name != '')
);

-- Create index on is_active for faster filtering
CREATE INDEX IF NOT EXISTS idx_models_is_active ON models(is_active);
CREATE INDEX IF NOT EXISTS idx_models_name ON models(model_name);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_models_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_models_updated_at
BEFORE UPDATE ON models
FOR EACH ROW
EXECUTE FUNCTION update_models_updated_at();

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON models TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON models TO service_role;
