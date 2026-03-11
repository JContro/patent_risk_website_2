## Summary

I've added error tracking and print statements to [`data_management/main.py`](data_management/main.py:1) to monitor parsing errors. Here's what was implemented:

### Changes Made:

1. **Added global error counters** (lines 1189-1200):
   - `xml_parse_errors` - XML parsing failures
   - `extract_patent_errors` - Failures when extracting patent data
   - `missing_root_tag_errors` - Unknown XML root tags
   - `keyword_filter_errors` - Keyword filtering failures
   - `other_errors` - Miscellaneous errors

2. **Added helper functions**:
   - [`reset_parsing_errors()`](data_management/main.py:1208) - Reset counters before each run
   - [`print_parsing_errors()`](data_management/main.py:1217) - Print error summary

3. **Added error tracking** in:
   - [`parse_xml_content()`](data_management/main.py:1233) - For batch XML parsing
   - [`process_xml_file_sequential()`](data_management/main.py:1134) - For streaming XML parsing
   - [`read_xml_content()`](data_management/main.py:1086) - For ZIP file handling

4. **Error summary is printed** at the end of each ZIP file processing

### Current Issue:

The ZIP files (e.g., `ipg230620.zip` at 120MB) contain **multiple concatenated XML documents** (multiple patents in a single file). The current `iterparse` approach only processes the **first patent** and then fails with "junk after document element" error when it encounters the second patent's XML declaration.

**Result**: Only 1 patent is extracted per ZIP file instead of all patents.

### Test Output:
```
✓ Processed 1 patents
✓ Saved 1 patents to database

PARSING ERROR SUMMARY
  XML Parse Errors:        1
  Extract Patent Errors:   0
  Missing Root Tag Errors: 0
  Keyword Filter Errors:   0
  Other Errors:            0
  TOTAL ERRORS:            1
```

To fully parse all patents from these large ZIP files, the code would need to either:
1. Split the file by `<?xml` declarations before parsing (but this requires loading the entire file into memory, causing OOM)
2. Use a streaming approach that can handle multiple XML documents
3. Process smaller chunks of the file
