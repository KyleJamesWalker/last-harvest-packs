# Last Harvest Packs

Mod packs for [Last Harvest](https://github.com/KyleJamesWalker/last-harvest), published at
[kylejameswalker.com/last-harvest-packs](http://www.kylejameswalker.com/last-harvest-packs/).

## Add a pack

1. Make a folder under `packs/`, named after the pack in lowercase, such as `packs/thank_you/`.
2. Put the `.pak` in it. A folder holds exactly one.
3. Add square JPG screenshots (480x480px) to `shots/` in that folder.
4. Add a `pack.toml`:

   ```toml
   title = "Thank You"
   author = "Your Name"
   game = "v0.9.0" # the release the pack was made for
   summary = "One sentence for the page."
   changes = ["Optional list of what the pack changes."]
   ```
5. Build and check the page, then open a pull request.

## Build

```sh
python3 -I tools/build.py
python3 -m http.server 8095 --directory _site
```

The build needs only Python 3.11 or later. It reads each pack's cards and props
from the `.pak`, and fails on a pack with no `manifest.toml`. Pushes to `main`
deploy the page with `.github/workflows/pages.yml`.

Only upload content you have the rights to share.
