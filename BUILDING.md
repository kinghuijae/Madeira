# Building Madeira

Madeira is intended to be buildable from a clean clone with one command.

For this personal fork's Windows editing and checks, see
[`docs/WINDOWS-DEVELOPMENT.md`](docs/WINDOWS-DEVELOPMENT.md). Building the IPA
still requires macOS and Xcode, locally or in the existing GitHub Actions workflow.

## Prerequisites

- macOS with a current Xcode installation and the iOS SDK
- Xcode command-line tools selected with `xcode-select`
- Homebrew
- Git
- Rust installed with [rustup](https://rustup.rs/)

The build script installs the remaining Homebrew packages, initializes all
submodules (including DXMT's nested header submodules), downloads the pinned compiler toolchains, builds the native iOS
libraries, downloads the official Microsoft Visual C++ x64 Redistributable,
extracts the required runtime DLLs locally, builds the Xcode project, and
packages the result. Microsoft runtime DLLs are never added to Git.
The pairing-library build installs the Rust iOS target and generates its crate notices.

Expect the first run to take several hours on a typical Mac: LLVM 15 is
compiled twice (macOS host tools, then the iOS target libraries), and FEX is
a large C++ codebase. Later runs reuse cached outputs and finish in minutes.

## Build an IPA

```sh
git clone --recurse-submodules https://github.com/willfaust/Madeira.git
cd Madeira
./tools/build-ipa.sh
```

The output is:

```text
dist/Madeira.ipa
```

The IPA is ad-hoc signed with Madeira's requested entitlements so that a
sideloading tool such as SideStore can re-sign it with the contributor's own
development identity.

The current native DXMT build targets iOS 18.0, so the packaged application
also uses iOS 18.0 as its effective deployment target.

## Re-running the build

Toolchains and expensive native build outputs are cached under their existing
ignored build directories. Re-running `./tools/build-ipa.sh` reconfigures the source builds and uses their incremental compile rules.
An existing archive alone does not skip these local source builds.

GitHub Actions runs once for each PR update, on every push to main, and on manual
requests. Documentation changes also start a run. A newer run cancels an older
run for the same PR or development branch. Main runs finish before the next
queued main run starts, so publication is not interrupted. Build copies under `codex/pr-build-*` also run on
push, so a PR head with merge conflicts can still produce an IPA.

CI can reuse a completed IPA when the checked-out Git tree, runner platform,
Xcode/SDK/compiler identity, runner image and build flags match. The Git tree
includes component pins and build scripts. A reused IPA must pass the ZIP and
bundle-layout checks before upload. GitHub's branch and PR cache access rules
still apply; an unrelated branch's cache is not a shared artifact store.

## Main build distribution

Successful `main` builds in `kinghuijae/Madeira` publish an individual
`ci-<run>-<attempt>-<sha>` prerelease, then update the `main-latest` prerelease:

- [SideStore source](https://github.com/kinghuijae/Madeira/releases/download/main-latest/source.json)
- [Latest main IPA](https://github.com/kinghuijae/Madeira/releases/download/main-latest/Madeira.ipa)

Add the source URL in SideStore, install Madeira from the source, then use its
update button when a new build appears. The first successful build containing
this configuration creates these URLs. No extra secrets or GitHub Pages setup
are needed; the release job uses its existing `contents: write` permission.

CI stamps the app and its extensions with version `0.<run>.<attempt>` before
ad-hoc signing. Local builds retain the Xcode project versions. A complete IPA
cache hit retains its embedded version, since its content has not changed.
The source generator reads the actual IPA's bundle identifier, version, size,
minimum OS version, signed entitlements and privacy descriptions. It omits
marketplace-only fields for SideStore compatibility.

Each source entry downloads its matching individual release, so an already
cached source remains usable during replacement of the fixed IPA URL. Uploads
are checked against GitHub's size and SHA-256 before advancing the channel;
`source.json` is uploaded after the IPA mirror. Individual releases are retained.
Failed builds and PRs do not publish. Re-running a commit older than the current
channel publishes only its individual release, without rolling back the channel.
As with other GitHub release asset replacements, the fixed URLs can briefly be
unavailable during replacement. A manually cancelled or failed upload can be
recovered by rerunning the workflow's failed release job.

## Component caching

On an IPA cache miss, the workflow builds the native stages in parallel. Their
cache keys include the relevant source pins, recipes and build environment.
Unrelated workflow edits do not invalidate LLVM or FEX. CI accepts a complete
restored FEX/DXMT output set; LLVM also checks its archive checksum list and
required headers. Its source-header cache does not need an LLVM Git checkout.
Each native stage also retains its outputs for one day as an artifact in the
same workflow run. If its cache is unavailable, the app first downloads that
stage's artifact for the planned SDK. If both stores are unavailable, it rebuilds
the missing component. This follows [Iridium's completed-component handoff](https://github.com/intraducine/iridium/blob/901c6ee74817dbcc377c99620108bcec0a72c15b/.github/workflows/build-unsigned-ipa.yml).
Local source builds keep their normal incremental path.

CI keeps separate caches for LLVM, FEX, the 32-bit Windows DLLs, the MinGW
toolchain, Wine host tools, GnuTLS, FFmpeg, FreeType, Rust pairing and native
DXMT. Each key includes its own recipes and source inputs. Native, Rust,
graphics and app settings have separate fingerprints. The Rust fingerprint
uses the compiler selected in the pairing crate's directory.

| Change | Outputs rebuilt on a cache miss |
| --- | --- |
| App source, resources, docs or unrelated workflow edits | App and IPA |
| FEX pin or recipe | FEX, app and IPA |
| Wine pin | Wine host tools, Windows DLLs, native DXMT, app and IPA |
| DXMT pin or shader-header recipe | Windows DLLs, native DXMT, app and IPA |
| LLVM recipe | LLVM, native DXMT, app and IPA |
| MinGW recipe | MinGW, Wine host tools, Windows DLLs, app and IPA |
| GnuTLS, FFmpeg or FreeType recipe/source | That library, app and IPA |
| Rust source, Cargo inputs, compiler or Rust flags | Pairing library, app and IPA |
| Native DXMT/converter source or Metal settings | Native DXMT, app and IPA |
| App configuration or MoltenVK setting | App and IPA |
| Xcode, SDK, native compiler/flags or runner image | Compiled dependencies, app and IPA |

The downloaded MinGW toolchain has its own host-platform and recipe key.
No cache uses a prefix fallback. An exact match for the old combined dependency
cache can seed the new separate caches. Missing pairing notices or LLVM
archives do not count as a complete restored build.

The host checks cover all 4,096 combinations of twelve representative source
changes, further Cargo/configuration inputs, and sixteen combinations of native,
Rust, graphics and app settings. These checks verify the declared invalidation
rules. The full workflow verifies the native build, IPA package and cache restores.
The preflight also checks Xcode source membership, native protection queries,
optional Vulkan linkage and the iOS pointer exports before the full app build.

You can override parallelism with, for example:

```sh
JOBS=4 ./tools/build-ipa.sh
```

If you already have an official `vc_redist.x64.exe`, avoid the download with:

```sh
VC_REDIST_X64="$HOME/Downloads/vc_redist.x64.exe" ./tools/build-ipa.sh
```
