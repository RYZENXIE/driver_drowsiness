# Driver Drowsiness Detection and Alert System

Camera driver ka face dekhta hai. Agar driver so jaaye, behosh ho jaaye ya face frame se gayab ho jaaye, to jor ki siren bajti hai.

## Files

| File | Kaam |
| --- | --- |
| `main.py` | Camera app: video padhta hai, detection chalata hai, alarm bajata hai |
| `logic.py` | Detection ka dimaag: EAR, MAR, head tilt aur alert levels (koi camera/sound dependency nahi) |
| `sounds.py` | `beep.wav` aur `siren.wav` khud bana deta hai |
| `test_logic.py` | Logic ke tests (camera ke bina chalte hain) |
| `requirements.txt` | Python packages |

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.9 to 3.12 recommended. Agar `mediapipe` install na ho, to Python version check karo (mediapipe naye Python versions ko late support karta hai).

## Run

```bash
python main.py                  # default webcam
python main.py --camera 1       # doosra camera
python main.py --video test.mp4 # video file se test
python main.py --mute           # bina sound ke test
```

Window band karne ke liye **Q** dabao.

**Pehle 3 second calibration hota hai**: camera ke saamne seedha dekho, aankhein khuli rakho. Isse system aapki aankhon ke hisaab se threshold set karta hai.

## Alert levels

| Level | Kab | Kya hota hai |
| --- | --- | --- |
| 1 Caution | Aankhein ~1 sec band, ya 2 minute me 2 baar yawn | Chhota beep |
| 2 Warning | Aankhein ~2 sec band, ya sir 3 sec tak tedha/jhuka | Jor ki siren (jab tak aankhein na khulein) |
| 3 Emergency | Aankhein 4 sec band, ya aankhein band + sir jhuka, ya face 3 sec gayab | Siren + red border, event `events.csv` me log |

Sab limits `logic.py` ke `Config` me hain. Apne hisaab se badal sakte ho.

## Test chalana

```bash
python test_logic.py
```

## Tuning tips

- Camera aankhon ki height par, seedha chehre ki taraf lagao.
- Roshni kam ho to infrared camera use karo.
- Sunglasses me aankhein nahi dikhti, to EAR kaam nahi karega.
- Bahut zyada false alarm aaye to `ear_ratio` kam karo ya `closed_warning` badhao.
- Alarm late aaye to `closed_warning` kam karo.

## Raspberry Pi

- Frame size 640x480 hi rakho (already set).
- Siren audio jack se bajao, ya GPIO relay se 12 V siren chalao.
- Pi par `pip install mediapipe` ke liye 64-bit OS chahiye.

## Limitations

Ye prototype hai, certified safety device nahi. Alarm sirf warning deta hai, gaadi nahi rokta. Asli gaadi me use karne se pehle alag-alag roshni, drivers aur chashme ke saath test karo.
