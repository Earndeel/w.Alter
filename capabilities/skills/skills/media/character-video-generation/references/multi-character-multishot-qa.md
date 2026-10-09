# Multi-character reference-to-multi-shot QA

Use this reference when a video brief supplies several character sheets and asks for a cinematic multi-cut clip.

## 1. Convert sheets into a clean anchor

Character sheets are identity references, not video keyframes. Passing them directly as keyframes can make the provider reproduce labels, pose studies, diagrams, or the board layout in the film.

Recommended sequence:

1. Pass every sheet to an image model as a reference image.
2. Ask for one clean cinematic opening frame containing exactly the requested characters in the target environment.
3. Explicitly exclude reference-board layout, names, labels, typography, logos, watermarks, extra people, and duplicate anatomy.
4. Visually inspect the anchor for each character’s signature silhouette, headwear, hairstyle, clothing colors, props, and proportions.
5. Use the clean anchor as the sole first-frame I2V input when the group composition matters.

The image prompt should distinguish identity from layout. Example structure:

> Use the attached character sheets only as identity and costume references. Do not reproduce the sheets, labels, names, diagrams, or typography. Show exactly [character list] together in [environment]. Preserve [identity anchors]. No extra people, text, logos, watermarks, duplicate limbs, or malformed hands.

## 2. Write a timed multi-shot prompt

For a 20-second request, provide 20 numbered one-second shot roles. Each shot should have one visible action and one clear camera change: wide, close-up, profile, overhead, low angle, over-the-shoulder, insert, tracking, or final group composition.

Include these global constraints:

- exactly the requested characters, with identity and wardrobe continuity;
- hard cuts, no fades or dissolves, and no single unbroken take;
- natural-speed movement with enough action to fill the requested duration;
- no reference sheets, written text, subtitles, logos, watermarks, extra people, duplicated characters, malformed hands, or unrequested violence;
- a final shot that restores a readable group composition.

“20 cuts” is ambiguous in provider language. Record both numbers during QA: sampled shot compositions and detected transitions. In the validated pattern, 20 distinct shots correspond to 19 transitions.

## 3. Generation and polling

Use first-frame I2V when the anchor’s opening pose, lighting, and group layout are load-bearing. Use provider-native reference-to-video when identity continuity through motion is more important than exact frame zero. Do not pass first-frame and reference-array conditioning together unless the provider contract explicitly allows it.

Submit once, persist the provider job ID, and poll the same ID until terminal success. Do not resubmit because the first poll is still `Generating`; a duplicate can spend another credit. Save the completed MP4 locally before QA.

## 4. Technical QA commands

Replace `final.mp4` with the actual artifact path.

```bash
ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=index,codec_type,codec_name,width,height,\
  sample_aspect_ratio,r_frame_rate,avg_frame_rate,nb_frames,\
  sample_rate,channels \
  -of json final.mp4

ffmpeg -hide_banner -loglevel error -i final.mp4 -f null -
```

Check the measured dimensions, not the provider’s `16:9` or `720p` label. Some FLUX 3 16:9-tier outputs measure 1280×704. If an exact 16:9 file is required, correct it without stretching the image:

```bash
ffmpeg -hide_banner -loglevel error -i source.mp4 \
  -vf 'pad=1280:720:0:8:color=black,setsar=1' \
  -map 0:v:0 -map 0:a:0 \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a copy -movflags +faststart final-16x9.mp4
```

If exact duration is required, trim video and audio explicitly before the final probe:

```bash
ffmpeg -hide_banner -loglevel error -i source.mp4 \
  -filter_complex '[0:v]trim=duration=20,setpts=PTS-STARTPTS[v];[0:a]atrim=duration=20,asetpts=PTS-STARTPTS[a]' \
  -map '[v]' -map '[a]' -c:v libx264 -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart final-20s.mp4
```

Require `duration=20.000000` and a video frame count consistent with the measured FPS (480 frames at 24 fps). Do not rely on container duration alone; audio can mask a short video stream.

## 5. Inspect cuts and identity

Create a one-frame-per-second contact sheet:

```bash
ffmpeg -hide_banner -loglevel error -i final.mp4 \
  -vf 'fps=1,scale=320:-2,tile=5x4:padding=4:margin=4' \
  -frames:v 1 -q:v 2 storyboard-1fps.jpg
```

Inspect all 20 cells left-to-right, top-to-bottom. Confirm that the compositions are distinct, each requested character’s identity anchors remain readable, and no reference-board residue, text, watermark, extra person, duplicated limb, or major morphing defect appears.

Use FFmpeg scene detection as a candidate-transition detector, not as the sole creative verdict. A practical low threshold for this class of output is 0.10:

```bash
ffmpeg -hide_banner -i final.mp4 \
  -vf 'select=gt(scene\,0.10),showinfo' -an -f null - \
  2> scene-scan.log
```

At this threshold, count `showinfo` `pts_time` entries. A strict threshold such as 0.25 may miss subtle cinematic cuts; a low threshold may report adjacent frames around one transition, so compare the timestamps with the storyboard rather than blindly treating every event as a separate shot.

Verify audio separately:

```bash
ffmpeg -hide_banner -i final.mp4 -af volumedetect -vn -f null - 2> audio-qa.log
```

Require a successful audio decode, non-silent samples, and sensible `mean_volume`/`max_volume`. If the prompt asks for no dialogue, ASR is optional; do not invent a script-compliance pass from the prompt alone.

## Release checklist

- [ ] Clean anchor inspected before I2V.
- [ ] One provider job submitted; task ID retained through polling.
- [ ] Completed MP4 downloaded locally.
- [ ] Measured dimensions and SAR satisfy the requested aspect ratio.
- [ ] Duration and video frame count satisfy the brief.
- [ ] Full FFmpeg decode exits cleanly.
- [ ] 1-fps storyboard visually inspected.
- [ ] Shot count and transition count reported separately when “cuts” is ambiguous.
- [ ] All requested characters remain recognizable across wide and close shots.
- [ ] No board layout, generated text, logo, watermark, extra person, or major anatomy failure.
- [ ] Audio stream present and independently decoded/measured.
- [ ] Delivered path points to the verified final file, not a provider preview URL.
