# Environment Setup

## Prerequisites

This measure requires the following to be installed and configured:

### Python Environment
- Python 3.8 or higher
- Conda or virtual environment manager
- OpenStudio 3.9.0+ with Python bindings

### Required Python Packages
```bash
pip install openstudio requests python-dotenv
```

### API Credentials

Two API credentials are required for this measure to function fully:

#### 1. EC3 (Building Transparency) API
- **Purpose:** Environmental Product Declaration (EPD) data for embodied carbon calculations
- **Setup:**
  1. Create account at [https://buildingtransparency.org](https://buildingtransparency.org)
  2. Generate API token in account settings
  3. Store token in `config.ini` at repository root:
     ```ini
     ec3_api_token = YOUR_EC3_API_TOKEN_HERE
     ```

#### 2. RSMeans API (Gordian)
- **Purpose:** Cost data lookup for construction materials and labor
- **Setup:**
  1. Obtain Gordian RSMeans API credentials from your organization
  2. Store credentials in `.env` file at repository root:
     ```ini
     client_id = YOUR_CLIENT_ID
     client_secret = YOUR_CLIENT_SECRET
     ```
  3. Or set as environment variables:
     ```bash
     export client_id=YOUR_CLIENT_ID
     export client_secret=YOUR_CLIENT_SECRET
     ```

### Configuration Files

#### config.ini
Located at repository root. Contains EC3 API token:
```ini
[api_keys]
ec3_api_token = YOUR_EC3_API_TOKEN_HERE
```

#### .env
Located at repository root. Contains RSMeans credentials (never commit to git):
```ini
client_id = your_gordian_client_id
client_secret = your_gordian_client_secret
```

## Running the Measure

### Via apply_measure.py
```bash
cd lib/measures/IncreaseInsulationRValueForExteriorWalls
python apply_measure.py
```

### Via OpenStudio Workflow
The measure can be included in OpenStudio `.osw` workflow files:
```json
{
  "measure_dir_name": "IncreaseInsulationRValueForExteriorWalls",
  "arguments": {
    "r_value": 20.0,
    "analysis_period": 30,
    "gwp_statistic": "median",
    "api_key": "YOUR_EC3_TOKEN",
    "insulation_material_type": "Fiberglass Batts",
    "calculate_costs": true,
    "use_custom_costs": false,
    "overhead_profit_percent": 10.0
  }
}
```

## Troubleshooting

### "EC3 API token not found"
- Verify `config.ini` exists at repository root
- Check token is correctly formatted
- Ensure token has not expired

### "RSMeans API credentials not found"
- Verify `.env` file exists and contains `client_id` and `client_secret`
- Check environment variables are set if using those instead
- Verify credentials are valid with your Gordian account

### "Model not found"
- Verify OSM file path is correct in `apply_measure.py`
- Ensure OSM file is compatible with OpenStudio 3.9.0+

## API Documentation References

- **EC3 API:** https://api.buildingtransparency.org/docs
- **RSMeans API:** https://api.gordian.com/docs
- **OpenStudio:** https://openstudio.net
