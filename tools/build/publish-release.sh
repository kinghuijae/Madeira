#!/usr/bin/env bash
set -euo pipefail

# Defense in depth: only this fork's successful main workflow calls this script.
[[ "$GITHUB_REPOSITORY" == kinghuijae/Madeira && "$GITHUB_REF" == refs/heads/main ]]
[[ "$GITHUB_EVENT_NAME" == push || "$GITHUB_EVENT_NAME" == workflow_dispatch ]]

tag="ci-${GITHUB_RUN_NUMBER}-${GITHUB_RUN_ATTEMPT}-${GITHUB_SHA:0:7}"
base="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}"
run_url="${base}/actions/runs/${GITHUB_RUN_ID}/attempts/${GITHUB_RUN_ATTEMPT}"
python3 tools/build/sidestore-source.py generate dist/Madeira.ipa \
  --repository "$GITHUB_REPOSITORY" --tag "$tag" --sha "$GITHUB_SHA" \
  --output dist/source.json
(cd dist && sha256sum Madeira.ipa source.json > SHA256SUMS)
checksum=$(sha256sum dist/Madeira.ipa | cut -d ' ' -f 1)
notes="$RUNNER_TEMP/release-notes.md"
cat > "$notes" <<EOF
Personal CI build of Madeira.

- Source commit: ${GITHUB_SHA}
- Build: ${run_url}
- IPA SHA-256: \`${checksum}\`
- SideStore source: ${base}/releases/download/main-latest/source.json
- Latest main IPA: ${base}/releases/download/main-latest/Madeira.ipa

Add the source.json URL in SideStore to receive main build updates.
This ad-hoc signed IPA needs re-signing with your own Apple ID and JIT setup.
Game compatibility has not been verified on a device.
EOF

verify_asset() {
  local release_tag="$1" file="$2" release_api asset size digest
  size=$(stat -c %s "dist/$file")
  digest=$(sha256sum "dist/$file" | cut -d ' ' -f 1)
  release_api=$(gh release view "$release_tag" --repo "$GITHUB_REPOSITORY" --json apiUrl --jq .apiUrl)
  asset=$(gh api "$release_api" \
    --jq ".assets[] | select(.name == \"$file\") | [.state, (.size | tostring), .digest] | join(\" \")")
  test "$asset" = "uploaded $size sha256:$digest"
}

# Preserve each build so a previously fetched source always downloads the IPA
# whose version/size it describes, even while the rolling alias is replaced.
gh release create "$tag" dist/Madeira.ipa dist/source.json dist/SHA256SUMS \
  --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" \
  --title "Madeira CI ${GITHUB_RUN_NUMBER}.${GITHUB_RUN_ATTEMPT} (${GITHUB_SHA:0:7})" \
  --notes-file "$notes" --draft --prerelease --latest=false
for file in Madeira.ipa source.json SHA256SUMS; do verify_asset "$tag" "$file"; done
gh release edit "$tag" --repo "$GITHUB_REPOSITORY" --draft=false --prerelease --latest=false
printf '### IPA release\n\n[%s](%s/releases/tag/%s)\n\nSHA-256: `%s`\n' \
  "$tag" "$base" "$tag" "$checksum" >> "$GITHUB_STEP_SUMMARY"

if gh release view main-latest --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
  # Re-running an older commit must not roll the main channel backwards.
  comparison=$(gh api "repos/$GITHUB_REPOSITORY/compare/main-latest...$GITHUB_SHA" --jq .status)
  if [[ "$comparison" != ahead && "$comparison" != identical ]]; then
    echo 'Main channel unchanged: this commit does not descend from main-latest.' >> "$GITHUB_STEP_SUMMARY"
    exit 0
  fi
else
  if ! gh api "repos/$GITHUB_REPOSITORY/git/ref/tags/main-latest" >/dev/null 2>&1; then
    gh api --method POST "repos/$GITHUB_REPOSITORY/git/refs" \
      -f ref=refs/tags/main-latest -f sha="$GITHUB_SHA" >/dev/null
  fi
  gh release create main-latest --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" \
    --title 'Madeira main (latest successful build)' --notes-file "$notes" \
    --verify-tag --draft --prerelease --latest=false
fi

# Main workflow runs are serialized and not auto-cancelled during publication.
# Upload/verify the mirror first, then publish the new source as the final asset.
gh release upload main-latest dist/Madeira.ipa dist/SHA256SUMS --clobber --repo "$GITHUB_REPOSITORY"
verify_asset main-latest Madeira.ipa
verify_asset main-latest SHA256SUMS
gh release upload main-latest dist/source.json --clobber --repo "$GITHUB_REPOSITORY"
verify_asset main-latest source.json
gh api --method PATCH "repos/$GITHUB_REPOSITORY/git/refs/tags/main-latest" \
  -f sha="$GITHUB_SHA" -F force=true >/dev/null
gh release edit main-latest --repo "$GITHUB_REPOSITORY" --notes-file "$notes" \
  --draft=false --prerelease --latest=false
printf '\n### Main channel\n\n[IPA](%s/releases/download/main-latest/Madeira.ipa)\n\n[SideStore source](%s/releases/download/main-latest/source.json)\n' \
  "$base" "$base" >> "$GITHUB_STEP_SUMMARY"
