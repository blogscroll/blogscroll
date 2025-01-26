#!/bin/bash
set -e  # Exit on error

issue_json="$1"
issue_number="$2"

file_path=$(echo "$issue_json" | jq -r '.file_path')
content=$(echo "$issue_json" | jq -r '.content' | sed 's/^/    /')

echo "Processing file: $file_path for issue #${issue_number}"

if [[ -f "$file_path" ]]; then
  if grep -q "#<issue_${issue_number}>" "$file_path"; then
    echo "TOML content found for issue #${issue_number}"

    echo "Amending file: $file_path"
    # Use awk for safer multi-line block replacement
    awk -v block_start="#<issue_${issue_number}>" \
        -v block_end="#</issue_${issue_number}>" \
        -v replacement="$content" \
        'BEGIN {found=0} 
         $0 ~ block_start {found=1; print $0; print replacement; next} 
         $0 ~ block_end {found=0} 
         !found {print}' "$file_path" > "${file_path}.tmp"

    mv "${file_path}.tmp" "$file_path"
    echo "File amended successfully."
  else
    echo "TOML content not found for issue #${issue_number}"

    echo "Appending TOML content to file: $file_path"
    echo -e "\n#<issue_${issue_number}>\n$content\n#</issue_${issue_number}>" >> "$file_path"
    echo "Content appended successfully."
  fi
else
  echo "File $file_path does not exist. Cannot amend or append."
  exit 1
fi
