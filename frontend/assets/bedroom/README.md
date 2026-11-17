# Photorealistic bedroom assets

These project-local assets were generated with the **built-in image_gen tool**, using the user's supplied bedroom image as the visual reference/edit target. They are visual assets only; model predictions and device states still come from the Python backend. No runtime image-generation service or API key is needed.

| Asset | Purpose |
| --- | --- |
| `daylight-v2.png` | Open-curtain room with all artificial lights off; the fan motor has no baked-in blades and the AC has no baked-in temperature. |
| `warm-light-v2.png` | Matching room with warm ceiling-cove, pendant, recessed and table lights on. |
| `curtains-closed-v2.png` | Matching closed-curtain photographic plate used only inside the moving fabric masks. |
| `curtains-closed-warm-v2.png` | Warmly lit closed-curtain state used to settle the animation into a seamless photographic view. |

All four plates are 1470 × 1070 pixels. Their source generation prompts are preserved verbatim in `generation-prompts.json`.

The scene is composed inline in `frontend/index.html`. Photos share the same SVG viewBox, so device alignment remains stable at every screen size. The warm-light photos crossfade according to the backend light state. Closed-curtain fabric is clipped into two moving panels behind a fixed mask that preserves the foreground bed and plant; open panels gather into the photographed side drapes. After closing, a matching full photographic state settles into place to preserve realistic occlusion and lighting without visible mask edges. A perspective transform keeps the rotating fan in the ceiling plane. The photographed AC receives a live temperature/status display and animated airflow.

`frontend/css/style.css` owns transitions and honors reduced motion. `frontend/js/bedroom.js` updates only from the server's authoritative state. The generated photos intentionally contain no UI text or static ON-state device animation.
