#4 start
import cv2
from PIL import Image
from google import genai

# 6-шы қатысушы осы жерге API кілтті қояды
API_KEY = "YOUR_API_KEY"
client = genai.Client(api_key=API_KEY)

def extract_frames(video_path, num_frames=5):
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    
    if total_frames <= 0:
        return frames

    step = max(1, total_frames // num_frames)
    for i in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if ret:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb_frame))
        if len(frames) >= num_frames:
            break
            
    cap.release()
    return frames

def check_video_safety(video_path):
    frames = extract_frames(video_path, num_frames=5)
    
    if not frames:
        return {"status": "Қате", "details": "Видео оқылмады"}

    prompt = (
        "Мына видео кадрларында төбелес (буллинг), қару-жарақ, қан, "
        "есірткі немесе 18+ қауіпті контент бар ма? "
        "Алдымен 'Қауіпсіз' немесе 'Қауіпті' деп жаз, "
        "сосын не табылғанын 1 сөйлеммен түсіндір."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, *frames]
        )
        result_text = response.text.strip()
        is_danger = "Қауіпті" in result_text or "Опасно" in result_text
        
        return {
            "status": "Опасно" if is_danger else "Безопасно",
            "details": result_text
        }
    except Exception as e:
        return {"status": "Қате", "details": str(e)}
#4 end
