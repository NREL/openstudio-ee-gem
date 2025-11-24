# Runner Output Formatting Improvements

## Overview
The `runner.registerInfo` messages in `measure.py` have been formatted to improve readability and provide better visual structure when viewing console output.

## Key Improvements

### 1. **Section Headers**
Added clear section headers with visual separators to organize output into logical groups:

```
================================================================================
SUBSURFACE DISCOVERY
================================================================================
Total sub-surfaces found: 25

--------------------------------------------------------------------------------
Filtering window subsurfaces...
--------------------------------------------------------------------------------
  ✓ Processing window: Window 1
  ✗ Skipping non-window surface: Door 1

================================================================================
WINDOW RENOVATION PROCESSING
================================================================================

────────────────────────────────────────────────────────────────────────────────
Processing: Window 1
────────────────────────────────────────────────────────────────────────────────
```

### 2. **Visual Indicators**
Added Unicode symbols to indicate status and improve scanning:

- ✓ (checkmark) - Successful operations
- ✗ (cross) - Skipped items
- → (arrow) - Actions being performed
- • (bullet) - Details and specifications
- ○ (circle) - Skipped renovations
- ⚠ (warning) - Non-critical warnings
- ℹ (info) - Informational messages

### 3. **Hierarchical Indentation**
Used consistent indentation to show relationships:

```
  → Creating new 2-pane window construction for Window 1
    ✓ Applied new construction 'Window_1_2_Pane' to Window 1
    
  → Adding glazing film effects to newly created construction for Window 1
    → Modified innermost glass pane with film properties:
      Visible Transmittance: 0.881 → 0.705
      Solar Transmittance: 0.775 → 0.543
      Back Emissivity: → 0.300
```

### 4. **Improved Material Output**
Made material-specific messages more concise and easier to read:

Before:
```
Calculating embodied carbon for glass using 2 pane(s) with thickness 0.003 m
Embodied carbon of glass in Window 1: 12.45 kg CO2 eq
```

After:
```
    • Glass: 2 pane(s) × 3.0mm thickness
    ✓ Glass: 12.45 kg CO2 eq
```

### 5. **Prominent Totals**
Made total embodied carbon values stand out with dedicated sections:

```
────────────────────────────────────────────────────────────────────────────────
  TOTAL EMBODIED CARBON FOR Window 1:
  45.32 kg CO2 eq
────────────────────────────────────────────────────────────────────────────────
```

### 6. **Concise Skip Messages**
Shortened messages for skipped options using consistent format:

Before:
```
No window frame renovation option selected, skip fetching window frame EPD data.
No glass pane renovation option selected, skip fetching glass pane EPD data.
```

After:
```
  ○ Window frame: No renovation selected, skipping EPD fetch
  ○ Glass pane: No renovation selected, skipping EPD fetch
```

### 7. **Better Construction Details**
Improved formatting for construction specifications:

Before:
```
Created 2-pane construction: glass thickness=3.0mm, gap thickness=12.7mm
```

After:
```
    • Created 2-pane construction
      Glass: 3.0mm | Air gap: 12.7mm
```

### 8. **Infiltration Processing Clarity**
Enhanced infiltration messages with better structure:

```
================================================================================
INFILTRATION PROCESSING
================================================================================
  ℹ Initial model contained 15 space infiltration objects

  ✓ Altered: Space Infiltration 1 50 percent reduction (Space Type: Office)
  ✓ Altered: Space Infiltration 2 50 percent reduction (Space: Office 101)
```

## Benefits

1. **Easier to Scan** - Clear sections and visual indicators allow quick navigation through output
2. **Better Context** - Hierarchical indentation shows relationships between operations
3. **Reduced Verbosity** - Concise messages without losing important information
4. **Professional Appearance** - Consistent formatting throughout makes output look polished
5. **Improved Debugging** - Clear structure makes it easier to identify where issues occur

## Example Full Output

```
================================================================================
SUBSURFACE DISCOVERY
================================================================================
Total sub-surfaces found: 30

--------------------------------------------------------------------------------
Filtering window subsurfaces...
--------------------------------------------------------------------------------
  ✓ Processing window: Window 1
  ✓ Processing window: Window 2
  ✗ Skipping non-window surface: Door 1

================================================================================
WINDOW RENOVATION PROCESSING
================================================================================

────────────────────────────────────────────────────────────────────────────────
Processing: Window 1
────────────────────────────────────────────────────────────────────────────────
  ℹ Number of panes: 2 (user-specified, applied to all windows)

  → Creating new 2-pane window construction for Window 1
    • Created 2-pane construction
      Glass: 3.0mm | Air gap: 12.7mm
    ✓ Applied new construction 'Window_1_2_Pane' to Window 1

  ○ Window frame: No renovation selected, skipping EPD fetch
  ○ Caulking: No renovation selected, skipping EPD fetch

    • Glass: 2 pane(s) × 3.0mm thickness
    ✓ Glass: 12.45 kg CO2 eq
    ✓ Frame: 8.32 kg CO2 eq
    ✓ Film: 2.15 kg CO2 eq

────────────────────────────────────────────────────────────────────────────────
  TOTAL EMBODIED CARBON FOR Window 1:
  22.92 kg CO2 eq
────────────────────────────────────────────────────────────────────────────────
```

## Compatibility

All Unicode symbols used are widely supported across modern terminals and should display correctly on:
- Windows PowerShell / Command Prompt
- Windows Terminal
- macOS Terminal
- Linux terminals (most common shells)
- VS Code integrated terminal

If Unicode symbols don't display properly in certain environments, they will typically fall back to similar ASCII characters or squares, but the structure and indentation will remain intact.
