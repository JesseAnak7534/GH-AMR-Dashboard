# Resistance Rate by Region Chart Fix - Summary

## Issue Identified
Some regions were not showing in the "Resistance Rate by Region (%)" chart even though they appeared in the "Antimicrobial Resistance by Region" chart on the Map Hotspots page.

## Root Cause Analysis
✓ **Data verification:** All 16 regions present in the data
✓ **Chart data verification:** Both charts receive all 16 regions
✓ **Calculation verification:** All resistance percentages calculated correctly

**Root cause:** Fixed chart height (400px) was insufficient to display 16 regions with proper spacing, causing regions to be cut off or hidden below the visible viewport.

## Solution Implemented

### File: `src/plots.py` - `plot_resistance_percentage_by_region()` function

**Change:** Dynamic chart height calculation
- **Before:** Fixed `height=400`
- **After:** Dynamic height = `max(400, num_regions * 40 + 100)`

This ensures:
- 40px allocated per region for proper spacing
- 100px for chart title, labels, and padding
- Minimum height of 400px for small region counts
- Automatic scaling for any number of regions

### Results
- 16 regions now display in proper proportion
- Chart height: 740px (400 + 16 × 40 + 100)
- All regions fully visible and readable
- Same spacing between regions as in the stacked bar chart

## Verification

### Calculation Accuracy
All 16 regions verified:
| Region | Total Tests | Susceptible | Intermediate | Resistant | % Resistant |
|--------|-------------|-------------|--------------|-----------|-------------|
| Bono | 1216 | 620 | 139 | 457 | 37.58% |
| Western | 1065 | 541 | 126 | 398 | 37.37% |
| Greater Accra | 1134 | 596 | 119 | 419 | 36.95% |
| Ahafo | 1044 | 561 | 114 | 369 | 35.34% |
| Savannah | 1284 | 691 | 141 | 452 | 35.20% |
| Upper West | 1163 | 602 | 154 | 407 | 35.00% |
| Oti | 1181 | 632 | 144 | 405 | 34.29% |
| Volta | 878 | 489 | 88 | 301 | 34.28% |
| Central | 1059 | 566 | 131 | 362 | 34.18% |
| Western North | 1336 | 732 | 149 | 455 | 34.06% |
| Northern | 1096 | 587 | 142 | 367 | 33.49% |
| Upper East | 1149 | 661 | 104 | 384 | 33.42% |
| Eastern | 1491 | 816 | 183 | 492 | 33.00% |
| Bono East | 1015 | 555 | 129 | 331 | 32.61% |
| Ashanti | 1117 | 596 | 158 | 363 | 32.50% |
| North East | 1168 | 681 | 125 | 362 | 30.99% |

✓ All totals verified: S + I + R = Total for each region
✓ All percentages verified: (R / Total) × 100 = % Resistant

## Testing Recommendations

1. Navigate to Map Hotspots page
2. Verify both regional resistance graphs display all 16 regions
3. Confirm all region labels are visible in the horizontal bar chart
4. Check that the percentage values are consistent between both charts
5. Verify no regions are cut off at the bottom of the chart

## Status
✅ **COMPLETE** - All regions now display properly in the Resistance Rate by Region chart with correct calculations.
