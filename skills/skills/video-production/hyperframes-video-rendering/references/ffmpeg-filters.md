# FFmpeg Video Post-Processing Filters

Verified filter chains that run successfully on ARM64 (Ubuntu 24.04, FFmpeg 6.1.1, libx264).

## Iphone Lowlight Look (720p→1080x1920)

Upscales 720x1280 to 1080x1920 with a phone-camera lowlight aesthetic:
- contrast + saturation + gamma lift
- S-curve via `curves` for cinematic contrast
- sharpening via `unsharp`
- vignette edges
- subtle chromatic aberration via `rgbashift`
- fine film grain via `noise`

```bash
ffmpeg -i input.mp4 -vf "
fps=30,
scale=1080:1920:force_original_aspect_ratio=increase,
crop=1080:1920,
eq=contrast=1.1:brightness=-0.01:saturation=1.08:gamma=1.06,
curves=all='0/0.02 0.25/0.20 0.75/0.80 1/0.96',
unsharp=5:5:0.85:3:3:0.35,
vignette=PI/7,
rgbashift=rh=1:bh=-1:edge=smear,
noise=alls=10:allf=t+u,
format=yuv420p
" -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p -c:a aac -b:a 128k output.mp4
```

Performance on ARM64 (8C/32G Oracle): ~43s for 15.5s video (0.35x realtime).

## Auto Exposure Pulsing Effect

Animated brightness/contrast that subtly pulses (sinusoidal, independent freq):
- brightness oscillates at 0.45 Hz ±0.8%
- contrast oscillates at 0.25 Hz ±1%
- fixed saturation boost (1.1)
- light noise + sharpening

```bash
ffmpeg -i input.mp4 -vf "
eq=brightness='0.008*sin(2*PI*t*0.45)':contrast='1.05+0.01*sin(2*PI*t*0.25)':saturation=1.1,
noise=alls=5:allf=t+u,
unsharp=5:5:0.6
" -c:v libx264 -crf 22 output.mp4
```

Performance on ARM64: ~13s for 15.5s video (1.2x realtime). Preserves original resolution.

## ARM64 Notes

- Both filters use `libx264` (software encoder) — no NVENC / hardware accel
- ARM64 NEON optimizations help but are slower than x86_64 for these filter chains
- `curves`, `noise`, and `rgbashift` are the most expensive filters
- For production pipelines, prefer a worker x86_64 machine to avoid ARM64 rendering bottlenecks
