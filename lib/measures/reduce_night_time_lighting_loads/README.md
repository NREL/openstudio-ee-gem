

###### (Automatically generated documentation)

# Reduce Night Time Lighting Loads

## Description


## Modeler Description


## Measure Type
ModelMeasure

## Taxonomy


## Arguments


### Pick a Lighting Definition From the Model (schedules using this will be altered)

**Name:** lights_def,
**Type:** Choice,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Fractional Value for Night Time Load

**Name:** fraction_value,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Apply Schedule Changes to Weekday and Default Profiles?

**Name:** apply_weekday,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Weekday/Default Time to Start Night Time Fraction(24hr, use decimal for sub hour).

**Name:** start_weekday,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Weekday/Default Time to End Night Time Fraction(24hr, use decimal for sub hour).

**Name:** end_weekday,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Apply schedule changes to Saturdays?

**Name:** apply_saturday,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Saturday Time to Start Night Time Fraction(24hr, use decimal for sub hour).

**Name:** start_saturday,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Saturday Time to End Night Time Fraction(24hr, use decimal for sub hour).

**Name:** end_saturday,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Apply Schedule Changes to Sundays?

**Name:** apply_sunday,
**Type:** Boolean,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Sunday Time to Start Night Time Fraction(24hr, use decimal for sub hour).

**Name:** start_sunday,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Sunday Time to End Night Time Fraction(24hr, use decimal for sub hour).

**Name:** end_sunday,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Material and Installation Costs per Light Quantity ($).

**Name:** material_cost,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Years Until Costs Start (whole years).

**Name:** years_until_costs_start,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### Expected Life (whole years).

**Name:** expected_life,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### O & M Costs Costs per Light Quantity ($).

**Name:** om_cost,
**Type:** Double,
**Units:** ,
**Required:** true,
**Model Dependent:** false

### O & M Frequency (whole years).

**Name:** om_frequency,
**Type:** Integer,
**Units:** ,
**Required:** true,
**Model Dependent:** false




