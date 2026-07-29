# Eosin_VRRenderer

## Overview

This is a GitHub version of [Eosin's VRRenderer Plugin](https://hub.virtamate.com/resources/video-renderer-for-3d-vr180-vr360-and-flat-2d-audio-bvh-animation-recorder.11994/) for Virt-A-Mate. See that link for further information.

This **isn't an official repository for the plugin**, but my (yunidatsu) private one for releasing some changes I'm doing to it.

## VAM-PIP still-capture API

The renderer exposes a narrow registered-storable API for deterministic still
captures. It does not accept an output directory; every result is written below
`Saves/VR_Videos_And_Funscripts/`.

Inputs:

* `VAMPipRequestId`
* `VAMPipBaseFilename`

Action:

* `VAMPipCapture`

Outputs:

* `VAMPipStatus`: `idle`, `rendering`, `encoding`, `succeeded`, or `failed`
* `VAMPipLastOutput`: the VaM-relative output path after `succeeded`
* `VAMPipError`: the error after `failed`

The request ID and base filename are sanitized to ASCII letters, digits,
underscores, and hyphens. The emitted filename is
`vampip_<request-id>_<base-filename>.jpg` or `.png`, according to the existing
Image Format setting. `succeeded` is published only after image encoding,
writing, and renderer cleanup have completed.

## License

Eosin released the plugin under CC BY-SA.

## Credits

Credit for this plugin goes mainly to Eosin. Further credits from the original release:

* Thanks to **MacGruber** for his previous work which this plugin builds and heavily relies upon!
* Thanks to **Élie Michel** for his LilyRender360 shader which is responsible for the 15x performance gain compared to a CPU-based implementation!
* Thanks to **kuler** for contributing the correct method to do transparent render in VaM!
* Thanks to **ragingsimian**, **morkork**, **VAMguy**, **3115062**, **Cleo** and **Vezezepu** for improvement suggestions!
