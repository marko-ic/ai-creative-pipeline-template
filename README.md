# AI Creative Pipeline — Template

A small scaffold for generating a **coherent set** of static ads for one brand.
No framework, one script.

This is an extract from a larger internal pipeline, reduced to the part that is
worth sharing: the method, and enough code to run it.

## The idea

Generating one good ad is easy. Generating twenty that look like they came from
the same brand is the actual problem.

The approach is to move the brand rules **into the prompt** rather than fixing
things afterwards. Every entry in `prompts.json` opens with the same
visual-system preamble — ground colour, exactly one accent colour, type register,
mood, and an explicit list of what must *not* appear. Only the concept below it
changes.

Where those values come from matters. Read them out of the brand's own site:
CSS custom properties and `@font-face` declarations give you exact hex codes and
real font names. Values you measured hold across a whole set. Values you
eyeballed drift by the fourth image.

## Setup

```sh
python3 -m pip install requests
cp .env.example .env            # add your API key
cp prompts.example.json prompts.json
```

## Running

```sh
python3 generate_ads.py --templates 1 --num-images 1 --resolution 1K   # smoke test
python3 generate_ads.py                                                # full run
```

Results land in `outputs/{NN}-{template_name}/`, with the exact prompt saved
next to each image as `prompt.txt` — so a result you like can be traced back to
what produced it.

Optional: drop logos, wordmarks or subject photos into `reference-images/`. Any
prompt with `"needs_product_images": true` is sent through the image-edit
endpoint with those as references instead of pure text-to-image.

## What this will not do for you

**A model treats rules as suggestions.** Even with the accent colour stated
three times, expect the occasional second accent, a broken wordmark, or a piece
of the prompt's own scaffolding drawn into the image. Review every asset before
it ships.

**Exact typography is the weak spot.** Photographic scenes, textures and macro
shots come back better than anything you would build by hand. Precise text is a
different matter — if a headline has to be pixel-accurate, render the type from
an HTML template over a generated background instead of asking the model for
both.

**`--num-images N` does not produce variants.** It sends the same prompt N times
and you get model scatter. Real variants need genuinely different prompts.

## Layout

```
generate_ads.py        the whole pipeline
prompts.example.json   schema + annotated starting point
reference-images/      optional refs for image-to-image prompts
outputs/               generated, gitignored
```

## License

MIT — see [LICENSE](LICENSE).
