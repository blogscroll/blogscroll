#!/bin/bash
set -e  # Exit on error

issue_json="$1"
file_path=$(echo "$issue_json" | jq -r '.file_path')
content=$(echo "$issue_json" | jq -r '.content')
issue_number="$2"

echo "Processing file: $file_path for issue #${issue_number}"

if [[ -f "$file_path" ]]; then
  if grep -q "#<issue_${issue_number}>" "$file_path"; then
    echo "TOML content found"
    echo "toml_found=true" >> $GITHUB_ENV

    echo "Amending file: $file_path for issue #${issue_number}"
    # Prepare the replacement block
    replacement_block=$(cat <<EOF
#<issue_${issue_number}>
$content
#</issue_${issue_number}>
EOF
    )

    # Use sed to replace the entire block
    sed -i "/#<issue_${issue_number}>/,/#<\/issue_${issue_number}>/c\\
$replacement_block" "$file_path"

    echo "File amended successfully."
  else
    echo "TOML content not found"
    echo "toml_found=false" >> $GITHUB_ENV
  fi
else
  echo "File $file_path does not exist"
  echo "toml_found=false" >> $GITHUB_ENV
fi

if [[ "$toml_found" == "false" ]]; then
  echo "Appending TOML content to file: $file_path for issue #${issue_number}"
  echo -e "\n#<issue_${issue_number}>\n$content\n#</issue_${issue_number}>" >> "$file_path"
  echo "Content appended successfully."
fi