#!/usr/bin/env bash
# Commits the staged changes through the GitHub GraphQL API, so GitHub signs them.
# Branch rulesets that require signed commits reject a plain `git push` from CI.
#
# Usage: commit-signed.sh <branch> <message> [<base>]
#   Without <base>: adds the commit on top of <branch> (creates it from HEAD if missing).
#   With <base>:    also opens a PR from <branch> into <base>, squash-merges it and
#                   deletes <branch>. Give each run a new branch name.
# Env:  GH_TOKEN  token with contents: write (and pull-requests: write with <base>)
#       GH_REPO   owner/repo of the checkout
# Run inside the target checkout. Needs git, gh, jq and base64 (all on GitHub runners).
# Large changes are split into several commits of at most COMMIT_BATCH_BYTES (base64).
set -euo pipefail

branch=$1 message=$2 base=${3:-}
repo=${GH_REPO:?GH_REPO must be set to owner/repo}
max_bytes=${COMMIT_BATCH_BYTES:-4000000}
cd "$(git rev-parse --show-toplevel)"

if git diff --cached --quiet; then echo "No staged changes."; exit 0; fi

local_head=$(git rev-parse HEAD)
head=$(gh api "repos/$repo/git/ref/heads/$branch" --jq .object.sha 2>/dev/null || true)
if [[ -z $head ]]; then
  gh api "repos/$repo/git/refs" -f ref="refs/heads/$branch" -f sha="$local_head" >/dev/null
  head=$local_head
elif [[ $head != "$local_head" ]]; then
  echo "Remote $branch is at $head, but local HEAD is $local_head. Pull first." >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
: > "$work/adds"; : > "$work/dels"

commit_batch() {
  jq -n --arg repo "$repo" --arg branch "$branch" --arg msg "$message" --arg head "$head" \
    --slurpfile adds "$work/adds" --slurpfile dels "$work/dels" '{
      query: "mutation($input: CreateCommitOnBranchInput!) { createCommitOnBranch(input: $input) { commit { oid } } }",
      variables: {input: {
        branch: {repositoryNameWithOwner: $repo, branchName: $branch},
        message: {headline: $msg},
        expectedHeadOid: $head,
        fileChanges: {additions: $adds, deletions: $dels}}}}' > "$work/payload.json"
  head=$(gh api graphql --input "$work/payload.json" --jq .data.createCommitOnBranch.commit.oid)
  [[ -n $head ]] || { echo "createCommitOnBranch returned no commit." >&2; exit 1; }
  echo "Signed commit $head on $branch"
  : > "$work/adds"; : > "$work/dels"
}

# Deletions are small; they all go into the first commit.
while IFS= read -r -d '' path; do
  jq -nc --arg path "$path" '{path: $path}' >> "$work/dels"
done < <(git diff --cached --no-renames --name-only --diff-filter=D -z)

# Read contents from the index, not the work tree, so line endings match what git stores.
size=0
while IFS= read -r -d '' path; do
  git cat-file blob ":$path" | base64 -w0 > "$work/b64"
  n=$(wc -c < "$work/b64")
  if (( size > 0 && size + n > max_bytes )); then commit_batch; size=0; fi
  jq -nc --arg path "$path" --rawfile contents "$work/b64" '{path: $path, contents: $contents}' >> "$work/adds"
  size=$((size + n))
done < <(git diff --cached --no-renames --name-only --diff-filter=d -z)
commit_batch

[[ -z $base ]] && exit 0

url=$(gh pr create --repo "$repo" --base "$base" --head "$branch" --title "$message" \
  --body "Automated update. Committed through the GitHub API, so GitHub signs it.")
echo "Opened $url"
# GitHub computes mergeability asynchronously, so the first attempts can fail.
for attempt in 1 2 3 4 5 6; do
  if gh pr merge "$url" --squash; then
    gh api -X DELETE "repos/$repo/git/refs/heads/$branch" >/dev/null || true
    exit 0
  fi
  sleep $((attempt * 5))
done
echo "Could not merge $url" >&2
exit 1
