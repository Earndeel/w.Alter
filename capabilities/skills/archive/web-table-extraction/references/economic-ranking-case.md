# Economic ranking table case

## Observed extraction pattern
A regional GDP ranking page exposed only its first rows in the browser snapshot, while the underlying HTML contained two complete tables with 43 rows each. A direct HTML fetch followed by table enumeration made the complete dataset available without heavier browser automation.

## Validation lessons
- Parallel tables represented different source vintages; header inspection and first-row checks were required before selecting one.
- The displayed abbreviated values were less suitable than the full-value column for unit conversion.
- The regional table mixed sovereign states with a dependent territory.
- The source's geographic perimeter excluded several states commonly included in a broader political definition of Europe.
- The answer needed an explicit distinction between total GDP at PPP and GDP at PPP per capita.

## Presentation pattern
State: metric, forecast year, unit, source vintage, and geographic perimeter. Remove non-sovereign territories only if the user requested countries, renumber after filtering, and disclose states lacking comparable source data.
