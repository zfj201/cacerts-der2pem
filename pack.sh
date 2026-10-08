#!/bin/sh
set -eu
cd "$(dirname "$0")"
D2P_SDK=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}
D2P_BUILD_TOOLS=${D2P_BUILD_TOOLS:-36.0.0}
D2P_PLATFORM=${D2P_PLATFORM:-android-36}
D2P_BUILD=$(mktemp -d)
trap 'rm -rf "$D2P_BUILD"' EXIT HUP INT TERM
mkdir "$D2P_BUILD/classes" "$D2P_BUILD/dex" "$D2P_BUILD/pkg"
javac --release 8 -d "$D2P_BUILD/classes" src/CertTool.java
java -cp "$D2P_SDK/build-tools/$D2P_BUILD_TOOLS/lib/d8.jar" com.android.tools.r8.D8 --min-api 26 \
  --lib "$D2P_SDK/platforms/$D2P_PLATFORM/android.jar" --output "$D2P_BUILD/dex" "$D2P_BUILD/classes/"*.class
(cd "$D2P_BUILD/dex" && zip -q "$D2P_BUILD/pkg/certtool.jar" classes.dex)
cp module.prop service.sh verify.sh customize.sh "$D2P_BUILD/pkg/"
chmod 0755 "$D2P_BUILD/pkg/"*.sh
(cd "$D2P_BUILD/pkg" && zip -q "$D2P_BUILD/cacerts-der2pem.zip" module.prop service.sh verify.sh customize.sh certtool.jar)
unzip -t "$D2P_BUILD/cacerts-der2pem.zip"
cp "$D2P_BUILD/pkg/certtool.jar" certtool.jar
mv "$D2P_BUILD/cacerts-der2pem.zip" cacerts-der2pem.zip
