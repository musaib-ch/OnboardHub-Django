import os
import glob
import re
import sys

def check():
    template_files = glob.glob('templates/**/*.html', recursive=True)
    split_tag_pattern = re.compile(r'(\{%|\{\{)[^%\n}]*$')
    errors = []
    
    for path in template_files:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for idx, line in enumerate(lines, 1):
                if split_tag_pattern.search(line):
                    errors.append((path, idx, line.strip()))

    if errors:
        print(f"[ERROR] Found {len(errors)} broken template tag(s):")
        for path, line_num, content in errors:
            print(f"  {path}:{line_num} -> {content}")
        sys.exit(1)
    else:
        print(f"[SUCCESS] All {len(template_files)} Django templates are clean and valid!")

if __name__ == "__main__":
    check()
