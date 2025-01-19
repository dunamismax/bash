#!/usr/bin/env bash
#
# install-nerd-fonts.sh
#
# Downloads and installs multiple Nerd Fonts on Ubuntu.
# Adjust BASE_URL to the release version you want (e.g., v3.0.2).
# Remove or comment out any fonts you do not need from the FONTS array.

set -e

BASE_URL="https://github.com/ryanoasis/nerd-fonts/releases/download/v3.3.0"
INSTALL_DIR="$HOME/.local/share/fonts"

# Create font directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# List of Nerd Font zip filenames you want to download.
# Below is a large subset of the ones you mentioned. Remove lines if you only want a few.
FONTS=(
  "0xProto.zip"
  "3270.zip"
  "Agave.zip"
  "AnonymousPro.zip"
  "Arimo.zip"
  "AurulentSansMono.zip"
  "BigBlueTerminal.zip"
  "BitstreamVeraSansMono.zip"
  "CascadiaCode.zip"
  "CascadiaMono.zip"
  "CodeNewRoman.zip"
  "ComicShannsMono.zip"
  "CommitMono.zip"
  "Cousine.zip"
  "D2Coding.zip"
  "DaddyTimeMono.zip"
  "DejaVuSansMono.zip"
  "DepartureMono.zip"
  "DroidSansMono.zip"
  "EnvyCodeR.zip"
  "FantasqueSansMono.zip"
  "FiraCode.zip"
  "FiraMono.zip"
  "GeistMono.zip"
  "Go-Mono.zip"
  "Gohu.zip"
  "Hack.zip"
  "Hasklig.zip"
  "HeavyData.zip"
  "Hermit.zip"
  "iA-Writer.zip"
  "IBMPlexMono.zip"
  "Inconsolata.zip"
  "InconsolataGo.zip"
  "InconsolataLGC.zip"
  "IntelOneMono.zip"
  "Iosevka.zip"
  "IosevkaTerm.zip"
  "IosevkaTermSlab.zip"
  "JetBrainsMono.zip"
  "Lekton.zip"
  "LiberationMono.zip"
  "Lilex.zip"
  "MartianMono.zip"
  "Meslo.zip"
  "Monaspace.zip"
  "Monofur.zip"
  "Monoid.zip"
  "Mononoki.zip"
  "MPlus.zip"
  "NerdFontsSymbolsOnly.zip"
  "Noto.zip"
  "OpenDyslexic.zip"
  "Overpass.zip"
  "ProFont.zip"
  "ProggyClean.zip"
  "Recursive.zip"
  "RobotoMono.zip"
  "ShareTechMono.zip"
  "SourceCodePro.zip"
  "SpaceMono.zip"
  "Terminus.zip"
  "Tinos.zip"
  "Ubuntu.zip"
  "UbuntuMono.zip"
  "UbuntuSans.zip"
  "VictorMono.zip"
  "ZedMono.zip"
)

echo "Downloading and installing Nerd Fonts into: $INSTALL_DIR"
sleep 2

# Download and install each .zip
for font_zip in "${FONTS[@]}"; do
  echo "--------------------------------------------------"
  echo "Downloading: $font_zip"
  wget -q --show-progress -O "/tmp/$font_zip" "$BASE_URL/$font_zip"

  echo "Extracting: $font_zip"
  unzip -o "/tmp/$font_zip" -d "$INSTALL_DIR" >/dev/null

  # Optional: remove the .zip to save space
  rm "/tmp/$font_zip"
done

# Update font cache
echo "Updating font cache..."
fc-cache -f -v

echo "All done! Nerd Fonts installed to $INSTALL_DIR."
