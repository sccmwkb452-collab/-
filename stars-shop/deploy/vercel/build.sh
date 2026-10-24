#!/bin/sh
# Vercel build (vercel.json "buildCommand"): the Mini App at /, the admin panel
# at /admin/, both in dist/. Vercel builds the Python function itself.
set -eu

# The Mini App signs visitors in with a demo key only when the API accepts it.
case "$(printf '%s' "${PUBLIC_DEMO:-true}" | tr 'A-Z' 'a-z')" in
  1 | true | yes | on) export VITE_PUBLIC_DEMO=1 ;;
  *) export VITE_PUBLIC_DEMO=0 ;;
esac

npm run build
rm -rf dist
mkdir -p dist
cp -R webapp/dist/. dist/
cp -R admin/dist dist/admin
