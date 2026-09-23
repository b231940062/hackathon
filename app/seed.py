"""Демо өгөгдөл.

Сервер анх асахад өгөгдлийн сан хоосон бол автоматаар ажиллана.
Дахин үүсгэх:  python -m app.seed --reset
"""
import math
import random
import shutil
import sys
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import DISTRICTS, STATUS_INFO, STATUSES
from app.database import Base, SessionLocal, engine
from app.models import (Comment, District, Issue, IssueImage, IssueStatusHistory, Khoroo, MPProfile, Notification,
                        OfficialResponse, Resolution, ResolutionConfirmation, Support, User)
from app.auth.security import hash_password
from app.services.images import generate_image
from app.services.priority import compute_priority
from app.utils import utcnow

ADMIN = {"email": "admin@holboos.mn", "name": "Холбоос Админ"}

MPS = [
    {"email": "mp@holboos.mn", "name": "Г.Бат-Эрдэнэ", "district": "Баянзүрх", "khoroos": [1, 2, 3, 4, 26],
     "constituency": "Баянзүрх дүүргийн тойрог", "position": "УИХ-ын гишүүн, Төсвийн байнгын хорооны гишүүн",
     "focus": ["road", "garbage", "lighting"],
     "bio": "Хот байгуулалт, дэд бүтцийн инженер. 15 жил нийслэлийн авто замын салбарт ажилласан. "
            "Иргэдийн санал хүсэлтийг ил тод, хугацаатай шийдвэрлэхийг зорьдог."},
    {"email": "narantuya@holboos.mn", "name": "Б.Нарантуяа", "district": "Сүхбаатар", "khoroos": list(range(1, 12)),
     "constituency": "Сүхбаатар дүүргийн тойрог", "position": "УИХ-ын гишүүн, Нийгмийн бодлогын байнгын хороо",
     "focus": ["safety", "heating", "education"],
     "bio": "Эрх зүйч, хүний эрхийн өмгөөлөгч. Хүүхэд, ахмад настны аюулгүй орчны төлөө ажилладаг."},
    {"email": "ganzorig@holboos.mn", "name": "Т.Ганзориг", "district": "Чингэлтэй",
     "khoroos": list(range(10, 20)), "constituency": "Чингэлтэй дүүргийн тойрог",
     "position": "УИХ-ын гишүүн, Эдийн засгийн байнгын хороо", "focus": ["water", "road", "garbage"],
     "bio": "Эдийн засагч. Гэр хорооллын дэд бүтэц, ус хангамжийн асуудлыг тэргүүлэх чиглэлээ болгосон."},
    {"email": "enkhtuya@holboos.mn", "name": "Д.Энхтуяа", "district": "Баянгол", "khoroos": list(range(1, 11)),
     "constituency": "Баянгол дүүргийн тойрог", "position": "УИХ-ын гишүүн, Боловсрол, соёлын байнгын хороо",
     "focus": ["education", "transport", "green"],
     "bio": "Багш, боловсролын менежер. Цэцэрлэг, сургуулийн хүртээмж, ногоон байгууламжийн төлөө."},
    {"email": "temuulen@holboos.mn", "name": "Б.Тэмүүлэн", "district": "Хан-Уул", "khoroos": list(range(11, 18)),
     "constituency": "Хан-Уул дүүргийн тойрог", "position": "УИХ-ын гишүүн, Эрүүл мэндийн дэд хороо",
     "focus": ["health", "road", "safety"],
     "bio": "Эмч, нийгмийн эрүүл мэндийн мэргэжилтэн. Шинэ хорооллын нийгмийн дэд бүтцийг хөгжүүлэхийн төлөө."},
    {"email": "zolboo@holboos.mn", "name": "Г.Золбоо", "district": "Сонгинохайрхан",
     "khoroos": list(range(18, 33)), "constituency": "Сонгинохайрхан дүүргийн тойрог",
     "position": "УИХ-ын гишүүн, Байгаль орчны байнгын хороо", "focus": ["air", "lighting", "health"],
     "bio": "Байгаль орчны инженер. Агаарын бохирдлыг бууруулах, гэр хорооллыг дахин төлөвлөх чиглэлээр ажилладаг."},
    {"email": "munkhbat@holboos.mn", "name": "Ц.Мөнхбат", "district": "Налайх", "khoroos": list(range(1, 9)),
     "constituency": "Налайх дүүргийн тойрог", "position": "УИХ-ын гишүүн", "focus": ["heating", "lighting"],
     "bio": "Уул уурхайн инженер. Алслагдсан дүүргүүдийн дэд бүтэц, нийтийн тээврийн хүртээмжийн төлөө."},
]

CITIZENS = [
    ("citizen@holboos.mn", "Д.Сарангэрэл", "Баянзүрх", 26, "99112233"),
    ("bold@holboos.mn", "Б.Болд", "Баянзүрх", 3, "88114455"),
    ("tsetseg@holboos.mn", "Н.Цэцэгмаа", "Баянзүрх", 1, "95118822"),
    ("solongo@holboos.mn", "Б.Солонго", "Баянзүрх", 4, "99004411"),
    ("uyanga@holboos.mn", "М.Уянга", "Баянзүрх", 2, "88990011"),
    ("temuujin@holboos.mn", "Э.Тэмүүжин", "Сүхбаатар", 8, "99667788"),
    ("oyunaa@holboos.mn", "Ж.Оюунаа", "Чингэлтэй", 15, "95553311"),
    ("anar@holboos.mn", "С.Анар", "Баянгол", 4, "88223344"),
    ("munkhzul@holboos.mn", "П.Мөнхзул", "Хан-Уул", 11, "99887766"),
    ("ganbold@holboos.mn", "О.Ганболд", "Хан-Уул", 17, "80112233"),
    ("erdene@holboos.mn", "Г.Эрдэнэбат", "Сонгинохайрхан", 20, "99335577"),
    ("nomin@holboos.mn", "Т.Номин", "Сонгинохайрхан", 25, "88447799"),
    ("khulan@holboos.mn", "А.Хулан", "Налайх", 2, "99221100"),
    ("batbayar@holboos.mn", "Д.Батбаяр", "Багануур", 3, "95669900"),
]

GIVEN_NAMES = ["Батбаяр", "Болормаа", "Ганбаатар", "Сарнай", "Энхжаргал", "Мөнхбаяр", "Отгонбаяр", "Нарангэрэл",
               "Батсайхан", "Оюунчимэг", "Төмөрбаатар", "Ариунаа", "Баярмаа", "Хишигт", "Золзаяа", "Дөлгөөн",
               "Мягмар", "Сүхбат", "Идэр", "Мишээл", "Анударь", "Билгүүн", "Энхтөр", "Цолмон", "Амаржаргал",
               "Ганчимэг", "Бямбасүрэн", "Нямдорж", "Удвал", "Эрдэнэчимэг", "Жаргалсайхан", "Тэнгис", "Номуун",
               "Халиун", "Мандах", "Ундрах", "Хонгорзул", "Батжаргал", "Пүрэвдорж", "Сэргэлэн"]
FATHER_INITIALS = list("БГДЭЖНОПСТЦЧХЛМА")

GENERIC_COMMENTS = [
    "Үнэхээр тийм, бид ч мөн адил хүндрэлтэй байна.",
    "Энэ асуудлыг аль эрт шийдэх ёстой байсан.",
    "Дэмжиж байна! Хурдан шийдэгдээсэй.",
    "Өнгөрсөн жил ч бас ийм байсан, энэ удаа л анхаараасай.",
    "Хорооны Засаг даргад мэдэгдсэн ч хариу ирээгүй.",
    "Би энэ хавьд амьдардаг, баталж байна.",
    "Хэдэн айлаараа гарын үсэг цуглуулж өгөх боломжтой.",
    "Ийм платформ байгаа нь сайн байна, ядаж хаана хүрснийг харж болж байна.",
    "Хөршүүддээ дэмжихийг хэлье.",
    "Хугацаатай төлөвлөгөө гаргаж өгөөч.",
    "Энэ бол олон хүний эрүүл мэнд, аюулгүй байдлын асуудал.",
]
PROGRESS_COMMENTS = [
    "Гишүүн хүлээж авсанд баярлалаа, үр дүнг нь хүлээж байна.",
    "Явцыг нь энд мэдээлж байгаа нь их зөв байна.",
    "Өнөөдөр ажилчид ирээд хэмжилт хийж байхыг харлаа.",
]
CATEGORY_COMMENTS = {
    "road": ["Машины дугуй хагарсан, нөхөн төлбөр авах боломжтой юу?", "Бороо орохоор ус тогтоод явах аргагүй болдог.",
             "Хүүхдүүд маань өдөр бүр энэ замаар сургуульдаа явдаг."],
    "garbage": ["Үнэр нь тэсвэрлэшгүй болсон.", "Хог ачих хуваарийг ил тод болгоосой.", "Нохойнууд хогийг тарааж байна."],
    "lighting": ["Орой харанхуй болохоор гарахаас айдаг болсон.", "Утасныхаа гэрлээр явж байна.",
                 "Энэ гудамжинд өнгөрсөн сард дээрэм гарсан."],
    "water": ["Өвлийн хүйтэнд ус хөлдөөд байгаа.", "Хувинтай ус зөөж байна.", "УСУГ-т залгахад утас авдаггүй."],
    "heating": ["Гэртээ хүрмээ өмсөөд сууж байна.", "Хүүхдүүд ханиад хүрээд байна.",
                "Цахилгаан халаагуураар аргацааж байна."],
    "air": ["Хүүхэд маань амьсгалын замын өвчнөөр 2 удаа эмнэлэгт хэвтсэн.", "Сайжруулсан түлшний цэг ойр байгаасай.",
            "Агаар цэвэршүүлэгч авах боломжгүй айл олон."],
    "transport": ["Ажилдаа 1 цаг хоцорч байна.", "Ахмад настнууд их хүндрэлтэй байна.", "Чиглэл нэмэх хэрэгтэй."],
    "safety": ["Хүүхдээ сургуульд нь хүргэж өгөхөөс өөр аргагүй болсон.", "Замын цагдаа байнга байлгаасай.",
               "Камер суурилуулаасай."],
    "education": ["Хүүхдээ цэцэрлэгт оруулах гэж 2 жил хүлээж байна.", "Хувийн цэцэрлэгийн төлбөр өндөр байна."],
    "health": ["Эмчид үзүүлэхийн тулд 2 цаг дугаарлаж байна.", "Хүүхдийн эмч хэрэгтэй байна."],
    "green": ["Хүүхдүүд тоглох газаргүй болсон.", "Хашаандаа мод тарих аян зохиоё."],
    "other": ["Дэмжиж байна."],
}

RECEIVED_TEXT = [
    "Таны асуудлыг хүлээн авлаа. Холбогдох мэдээллийг судалж, ажлын 5 хоногт багтаан хариу өгнө.",
    "Асуудлыг хүлээн авч, тойргийн ажлын албанд судлуулахаар өглөө. Явцыг энд тогтмол мэдээлнэ.",
]
REVIEW_TEXT = [
    "Дүүргийн Засаг даргын Тамгын газраас мэдээлэл авч, газар дээр нь очиж танилцлаа. Шалгалтын дүнг удахгүй мэдээлнэ.",
    "Тойргийн ажлын алба газар дээр нь очиж нөхцөл байдлыг судаллаа. Шийдвэрлэх хувилбарыг холбогдох газартай хэлэлцэж байна.",
]
IN_PROGRESS_TEXT = "{org} ажлын хэсэг гарган ажлыг эхлүүлсэн. Ажил ойролцоогоор 2 долоо хоногт дуусна."

ISSUES = [
    # ---------- Баянзүрх (mp@holboos.mn: 1, 2, 3, 4, 26-р хороо) ----------
    dict(title="3-р хорооны тоглоомын талбайн савлуур эвдэрсэн",
         desc="Манай байрны хашаан дахь хүүхдийн тоглоомын талбайн савлуурын гинж тасарч, гулсуурын төмөр хэсэг "
              "хугарсан. Өдөр бүр 30-40 хүүхэд тоглодог тул осол гарах эрсдэлтэй байна. Хорооны Засаг даргад амаар "
              "хэлсэн ч засагдаагүй.",
         cat="green", d="Баянзүрх", k=3, loc="13-р хороолол, 35-р байрны хашаа", urg="high", scope="street",
         status="IN_PROGRESS", days=21, sup=46, author="citizen@holboos.mn", ncom=6),
    dict(title="4-р хорооны гудамжны гэрэлтүүлэг ажиллахгүй байна",
         desc="Их тойруугаас 4-р хорооны гэр хороолол руу орох 600 метр гудамжны 12 гэрэлтүүлгийн 9 нь 2 сараас "
              "хойш асахгүй байна. Орой ажлаас харьж яваа эмэгтэйчүүд, сурагчид харанхуйд явахаас айдаг болсон.",
         cat="lighting", d="Баянзүрх", k=4, loc="4-р хорооны төв гудамж", urg="high", scope="khoroo",
         status="UNDER_REVIEW", days=12, sup=58, author="solongo@holboos.mn", ncom=7),
    dict(title="26-р хорооны хогийн цэг дүүрч, хог овоорсон",
         desc="26-р хорооны 5-р гудамжны хогийн цэгээс 2 долоо хоног хог ачаагүй. Хог салхинд хийсэж, эргэн "
              "тойрон золбин нохой, хархны үүр болж байна. Ойролцоо цэцэрлэг, сургууль бий.",
         cat="garbage", d="Баянзүрх", k=26, loc="26-р хороо, 5-р гудамжны хогийн цэг", urg="critical",
         scope="street", status="NEW", days=2, sup=38, author="citizen@holboos.mn", ncom=5),
    dict(title="2-р хорооны орон сууцанд халуун ус 10 хоног тасарсан",
         desc="2-р хорооны 18, 19, 20-р байранд халуун ус 10 хоног тасарсан. УСУГ-т 3 удаа залгасан ч "
              "'засвар хийгдэж байна' гэхээс өөр хариу өгөөгүй. Ахмад настан, нялх хүүхэдтэй айлууд хүндрэлтэй байна.",
         cat="water", d="Баянзүрх", k=2, loc="2-р хороо, 18-20-р байр", urg="high", scope="street",
         status="FORWARDED", days=9, sup=31, author="uyanga@holboos.mn", ncom=4,
         org="Нийслэлийн Ус сувгийн удирдах газар (УСУГ)"),
    dict(title="Автобусны буудлын хамгаалах байрны шил хагарсан",
         desc="1-р хорооны 'Цайз' буудлын хамгаалах байрны шил хагарч, суудал эвдэрсэн. Хүйтэнд ахмад настнууд "
              "салхинд зогсож автобус хүлээж байна. Хагархай шил хүүхдүүдэд аюултай.",
         cat="transport", d="Баянзүрх", k=1, loc="Цайз буудал, Энхтайвны өргөн чөлөө", urg="medium",
         scope="street", status="RESOLVED", days=34, sup=27, author="citizen@holboos.mn", ncom=5,
         org="Нийслэлийн Нийтийн тээврийн газар", confirm_yes=6, author_confirms=False,
         resolution=dict(
             explanation="Нийслэлийн Нийтийн тээврийн газартай хамтран 'Цайз' буудлын хамгаалах байрыг бүрэн шинэчиллээ.",
             action="Хагарсан шилийг бат бөх хамгаалалттай шилээр сольж, суудлыг шинээр суурилуулсан. Буудлын "
                    "тэмдэг, чиглэлийн мэдээллийн самбарыг шинэчилсэн.",
             response="Иргэдийн идэвхтэй мэдээллийн ачаар асуудлыг 3 долоо хоногт шийдвэрлэлээ. Баярлалаа!")),
    dict(title="20-р хорооны гэр хорооллын утаа хэт их байна",
         desc="Орой 19-22 цагийн хооронд утаа маш их болж, агаарын чанарын индекс 400 давж байна. Сайжруулсан түлш "
              "хүрэлцэхгүй, зарим айл түүхий нүүрс түлж байна. Хүүхдүүд амьсгалын замын өвчнөөр ойр ойрхон өвдөж байна.",
         cat="air", d="Баянзүрх", k=20, loc="20-р хороо, Шархад", urg="high", scope="district",
         status="RECEIVED", days=6, sup=64, author="bold@holboos.mn", ncom=8),
    dict(title="Сургуулийн урд гарцанд хурд сааруулагч хэрэгтэй",
         desc="3-р хорооны сургуулийн урдах замаар машинууд хурдтай явдаг. Энэ онд 2 удаа хүүхэд мөргүүлэх дөхсөн. "
              "Хурд сааруулагч, гэрлэн дохио, гарцны тэмдэг яаралтай хэрэгтэй.",
         cat="safety", d="Баянзүрх", k=3, loc="3-р хороо, сургуулийн урд", urg="critical", scope="khoroo",
         status="NEW", days=1, sup=12, author="tsetseg@holboos.mn", ncom=2),
    # ---------- Сүхбаатар ----------
    dict(title="Их тойруугийн явган хүний гарцны гэрлэн дохио ажиллахгүй",
         desc="1-р хорооны Их тойруугийн явган хүний гарцны гэрлэн дохио 3 долоо хоног ажиллахгүй байна. Оргил цагт "
              "явган зорчигчид машины дундуур гүйж гарч байна.",
         cat="safety", d="Сүхбаатар", k=1, loc="Их тойруу, Төв шуудангийн орчим", urg="critical", scope="khoroo",
         status="RESOLVED", days=40, sup=73, author="temuujin@holboos.mn", ncom=6,
         org="Нийслэлийн Авто замын газар", confirm_yes=9,
         resolution=dict(
             explanation="Гэрлэн дохионы удирдлагын блок шатсан байсныг сольж, гарцыг шинэчиллээ.",
             action="Удирдлагын блокыг сольж, явган хүний товчлуурт гэрлэн дохио суурилуулсан. Гарцны будгийг "
                    "шинэчилж, 'Явган хүний гарц' тэмдэг нэмсэн.",
             response="Замын хөдөлгөөний аюулгүй байдлыг хангах ажлыг 10 хоногт хийж гүйцэтгэлээ.")),
    dict(title="8-р хорооны орон сууцны дулаан хангалтгүй",
         desc="Байрны радиатор бүлээн ч болохгүй, өрөөний температур 14-15 хэм байна. Нийт 60 айл өрх "
              "цахилгаан халаагуур ашиглаж, цахилгааны төлбөр 2 дахин өссөн.",
         cat="heating", d="Сүхбаатар", k=8, loc="8-р хороо, 42-р байр", urg="high", scope="street",
         status="IN_PROGRESS", days=16, sup=52, author="temuujin@holboos.mn", ncom=6,
         org="Улаанбаатар Дулааны сүлжээ ТӨХК"),
    dict(title="Сэлбэ голын эргийн явган замын хавтан хөндийрсөн",
         desc="Сэлбэ голын эрэг дагуух явган замын хавтангууд хөндийрч, зарим нь хагарсан. Дугуйтай тэрэгтэй "
              "ээжүүд, тэргэнцэртэй иргэд явах боломжгүй болсон.",
         cat="road", d="Сүхбаатар", k=11, loc="Сэлбэ голын эрэг, 11-р хороо", urg="medium", scope="khoroo",
         status="UNDER_REVIEW", days=7, sup=19, ncom=3),
    # ---------- Чингэлтэй ----------
    dict(title="Гэр хорооллын шатны гишгүүр эвдэрч гулгаатай болсон",
         desc="15-р хорооны уулын энгэр дээрх гэр хороолол руу гарах бетон шатны гишгүүрүүд эвдэрч, өвөл мөсөөр "
              "хучигдаж маш гулгаатай болдог. Өнгөрсөн сард ахмад настан унаж гэмтсэн.",
         cat="road", d="Чингэлтэй", k=15, loc="15-р хороо, Хайлааст", urg="high", scope="street",
         status="NEW", days=3, sup=22, author="oyunaa@holboos.mn", ncom=3),
    dict(title="19-р хорооны ус түгээх байр 5 хоног хаалттай",
         desc="19-р хорооны ус түгээх байр 5 хоног хаалттай байна. 300 гаруй өрх 2 км зайтай өөр байраас ус зөөж "
              "байна. Ямар ч мэдэгдэл, тайлбар өгөөгүй.",
         cat="water", d="Чингэлтэй", k=19, loc="19-р хороо, 3-р ус түгээх байр", urg="critical", scope="khoroo",
         status="RECEIVED", days=5, sup=41, ncom=5),
    dict(title="12-р хороонд хогны машин 2 долоо хоног ирээгүй",
         desc="12-р хорооны гэр хороолол руу хогны машин 2 долоо хоног ирээгүй. Айлууд хогоо гудамжинд гаргаж "
              "тавьснаас эргэн тойрон бохирдож байна.",
         cat="garbage", d="Чингэлтэй", k=12, loc="12-р хороо, Дамбадаржаа", urg="high", scope="khoroo",
         status="RESOLVED", days=28, sup=35, author="oyunaa@holboos.mn", ncom=6, org="Нийслэлийн Тохижилтын удирдах газар",
         confirm_yes=3, confirm_no=2, dispute=True,
         resolution=dict(
             explanation="Хог тээврийн компанитай уулзаж, хуваарийг шинэчиллээ.",
             action="Хуримтлагдсан хогийг 2 өдрийн дотор ачуулж, долоо хоногт 2 удаа хог ачих хуваарь тогтоосон.",
             response="Хог ачилтыг хэвийн болголоо. Цаашид хуваарийн дагуу явагдана.")),
    # ---------- Баянгол ----------
    dict(title="3, 4-р хорооллын уулзварт гэрлэн дохио буруу тохируулагдсан",
         desc="3, 4-р хорооллын уулзварын гэрлэн дохионы хугацаа буруу тохируулагдсанаас өглөө, оройн оргил цагт "
              "30-40 минутын түгжрэл үүсч байна. Түргэн тусламжийн машин ч гарч чадахгүй байна.",
         cat="transport", d="Баянгол", k=4, loc="3, 4-р хорооллын уулзвар", urg="high", scope="district",
         status="FORWARDED", days=11, sup=88, author="anar@holboos.mn", ncom=8, org="Нийслэлийн Авто замын газар"),
    dict(title="Орон сууцны хонгилд ус алдаж, мөөгөнцөр үүссэн",
         desc="10-р хорооны 12-р байрны хонгилын ус дамжуулах хоолой цоорч, 2 сар ус алдаж байна. Давхарт мөөгөнцөр "
              "үүсч, үнэр гарч байна.",
         cat="water", d="Баянгол", k=10, loc="10-р хороо, 12-р байр", urg="medium", scope="street",
         status="RESOLVED", days=45, sup=17, ncom=4, org="Нийслэлийн Ус сувгийн удирдах газар (УСУГ)", confirm_yes=4,
         resolution=dict(
             explanation="УСУГ-ын засварын баг хонгилын шугамыг шинэчилсэн.",
             action="Цоорсон 24 метр ган хоолойг полипропилен хоолойгоор сольж, хонгилыг хатааж, "
                    "мөөгөнцрийн эсрэг цэвэрлэгээ хийсэн.",
             response="Засварын ажил бүрэн дууслаа. Иргэдэд хүлээцтэй хандсанд баярлалаа.")),
    dict(title="Цэцэрлэгт хүрээлэнгийн сандал, гэрэлтүүлэг эвдэрсэн",
         desc="6-р хорооны цэцэрлэгт хүрээлэнгийн сандлуудын ихэнх нь эвдэрсэн, гэрэлтүүлэг ажиллахгүй. Оройн "
              "цагаар согтуу хүмүүс цуглардаг болсон.",
         cat="green", d="Баянгол", k=6, loc="6-р хорооны цэцэрлэгт хүрээлэн", urg="medium", scope="khoroo",
         status="IN_PROGRESS", days=19, sup=29, ncom=4, org="Нийслэлийн Тохижилтын удирдах газар"),
    dict(title="10-р хорооны цэцэрлэгийн хүртээмж хүрэлцэхгүй",
         desc="10-р хороонд 2-5 насны 900 гаруй хүүхэд байгаа ч улсын цэцэрлэг ганцхан. Хүлээлгийн жагсаалтад "
              "300 гаруй хүүхэд байна.",
         cat="education", d="Баянгол", k=10, loc="10-р хороо", urg="medium", scope="district",
         status="UNDER_REVIEW", days=14, sup=57, author="anar@holboos.mn", ncom=6),
    # ---------- Хан-Уул ----------
    dict(title="Яармагийн гол замын нүх, эвдрэл",
         desc="Яармагийн гол замын 11-р хорооны хэсэгт том нүхнүүд үүсч, 2 машин дугуйгаа хагалсан. Бороо орохоор "
              "нүхэнд ус тогтож, харагдахгүй болдог.",
         cat="road", d="Хан-Уул", k=11, loc="Яармагийн гол зам", urg="high", scope="district",
         status="RESOLVED", days=38, sup=96, author="munkhzul@holboos.mn", ncom=8, org="Нийслэлийн Авто замын газар",
         confirm_yes=11, confirm_no=1,
         resolution=dict(
             explanation="Нийслэлийн Авто замын газар 1.2 км замын хучилтыг шинэчиллээ.",
             action="Эвдэрсэн хэсгийн хучилтыг хуулж, шинээр асфальтбетон хучилт хийсэн. Замын тэмдэглэгээг "
                    "шинэчилж, ус зайлуулах суваг цэвэрлэсэн.",
             response="Замын засварын ажил хугацаандаа дууслаа. Иргэдэд хүлээцтэй хандсанд баярлалаа.")),
    dict(title="Зайсангийн замаар ачааны машин хэт их явж байна",
         desc="Шөнийн цагаар Зайсангийн гудамжаар хүнд даацын ачааны машин их явж, байрнууд чичирч, "
              "замын хучилт эвдэрч байна.",
         cat="safety", d="Хан-Уул", k=13, loc="13-р хороо, Зайсан", urg="medium", scope="khoroo",
         status="NEW", days=4, sup=15, ncom=2),
    dict(title="17-р хорооны шинэ хороололд өрхийн эмнэлэг байхгүй",
         desc="17-р хорооны шинэ хороололд 12 мянга гаруй иргэн амьдардаг ч өрхийн эрүүл мэндийн төв байхгүй. "
              "Хамгийн ойрын эмнэлэг 5 км зайтай.",
         cat="health", d="Хан-Уул", k=17, loc="17-р хороо", urg="high", scope="district",
         status="UNDER_REVIEW", days=10, sup=67, author="ganbold@holboos.mn", ncom=6),
    # ---------- Сонгинохайрхан ----------
    dict(title="Толгойтын гэр хорооллын агаарын бохирдол",
         desc="Толгойтын гэр хороололд өвлийн улиралд утаа хэт их байна. Сайжруулсан түлшний цэг хол, дулаалгын "
              "хөтөлбөрт хамрагдаагүй айл олон.",
         cat="air", d="Сонгинохайрхан", k=20, loc="20-р хороо, Толгойт", urg="high", scope="district",
         status="IN_PROGRESS", days=25, sup=110, author="erdene@holboos.mn", ncom=9,
         org="Нийслэлийн Агаарын чанарын алба"),
    dict(title="Гэрэлтүүлэггүй гудамжинд гэмт хэрэг гарч байна",
         desc="25-р хорооны гудамжинд гэрэлтүүлэг огт байхгүй. Сүүлийн 2 сард 3 удаа дээрэм гарсан. "
              "Иргэд оройн цагаар гадагш гарахаас айж байна.",
         cat="lighting", d="Сонгинохайрхан", k=25, loc="25-р хороо, 7-р гудамж", urg="critical", scope="street",
         status="RECEIVED", days=8, sup=44, author="nomin@holboos.mn", ncom=5),
    dict(title="32-р хорооны өрхийн эмнэлэгт эмч хүрэлцэхгүй",
         desc="32-р хорооны өрхийн эрүүл мэндийн төвд 2 эмч 8000 гаруй иргэнд үйлчилж байна. Дугаар авахын тулд "
              "өглөө 6 цагаас дугаарлаж байна.",
         cat="health", d="Сонгинохайрхан", k=32, loc="32-р хорооны ӨЭМТ", urg="high", scope="khoroo",
         status="NEW", days=5, sup=26, ncom=3),
    dict(title="18-р хорооны үерийн далан эвдэрсэн",
         desc="18-р хорооны үерийн хамгаалалтын далан 30 метр газар нурсан. Зуны бороогоор гэр хороолол руу "
              "үер орох эрсдэлтэй.",
         cat="road", d="Сонгинохайрхан", k=18, loc="18-р хороо, үерийн далан", urg="critical", scope="khoroo",
         status="RESOLVED", days=60, sup=51, ncom=5, org="Онцгой байдлын ерөнхий газар", confirm_yes=7,
         resolution=dict(
             explanation="Онцгой байдлын газар, дүүргийн ЗДТГ хамтран далангийн нурсан хэсгийг сэргээлээ.",
             action="30 метр далангийн хэсгийг бетон блокоор бэхэлж, ус зайлуулах хоолой суурилуулсан.",
             response="Үерийн эрсдэлийг бууруулах ажил бүрэн дууслаа.")),
    # ---------- Налайх ----------
    dict(title="Налайхын төв замын гудамжны гэрэлтүүлэг асахгүй",
         desc="Налайхын төв замын 2-р хорооны хэсэгт гудамжны гэрэлтүүлэг 1 сар асахгүй байна. Шөнө явган "
              "зорчигчид машинд харагдахгүй аюултай.",
         cat="lighting", d="Налайх", k=2, loc="Налайх, төв зам", urg="high", scope="khoroo",
         status="RESOLVED", days=50, sup=33, author="khulan@holboos.mn", ncom=4,
         org="Улаанбаатар Цахилгаан түгээх сүлжээ ТӨХК", confirm_yes=5,
         resolution=dict(
             explanation="Цахилгаан түгээх сүлжээ кабелийн гэмтлийг засварласан.",
             action="Газар доорх кабелийн 2 гэмтлийг засаж, 18 гэрэлтүүлгийн чийдэнг LED-ээр сольсон.",
             response="Гэрэлтүүлэг бүрэн хэвийн ажиллаж байна.")),
    dict(title="4-р хорооны сургуулийн дулааны шугам хуучирсан",
         desc="Налайхын 4-р хорооны сургуулийн дулааны шугам хуучирч, анги танхимын температур 12-14 хэм байна. "
              "Сурагчид хүрэмтэйгээ хичээллэж байна.",
         cat="heating", d="Налайх", k=4, loc="4-р хорооны сургууль", urg="high", scope="khoroo",
         status="FORWARDED", days=13, sup=39, ncom=4, org="Улаанбаатар Дулааны сүлжээ ТӨХК"),
    # ---------- Багануур (оноогдсон гишүүнгүй) ----------
    dict(title="Багануураас хот руу явах автобусны тоо хүрэлцэхгүй",
         desc="Багануур - Улаанбаатар чиглэлийн автобус өдөрт 2 удаа л явдаг. Хотод ажилладаг, сурдаг иргэд "
              "их хүндрэлтэй байна.",
         cat="transport", d="Багануур", k=3, loc="Багануур, автобусны төв буудал", urg="medium", scope="district",
         status="NEW", days=7, sup=21, author="batbayar@holboos.mn", ncom=3),
]

DISPUTE_REASONS = [
    "Хуваарь гарсан ч өнгөрсөн долоо хоногт дахиад машин ирээгүй. Хог дахин овоорч эхэлсэн.",
    "Манай гудамжинд хог ачилт хэвийн болоогүй хэвээр байна.",
]


def _khoroo_coords(district_lat, district_lng, number, count):
    spread = 0.006 + 0.0006 * count
    r = spread * math.sqrt(number / max(1, count))
    angle = number * 2.39996
    return district_lat + r * math.sin(angle), district_lng + 1.45 * r * math.cos(angle)


def _seed_geo(db: Session) -> tuple[dict, dict]:
    districts, khoroos = {}, {}
    for name, name_en, count, lat, lng in DISTRICTS:
        d = District(name=name, name_en=name_en, lat=lat, lng=lng)
        for n in range(1, count + 1):
            klat, klng = _khoroo_coords(lat, lng, n, count)
            d.khoroos.append(Khoroo(number=n, lat=round(klat, 5), lng=round(klng, 5)))
        db.add(d)
        districts[name] = d
    db.flush()
    for d in districts.values():
        for k in d.khoroos:
            khoroos[(d.name, k.number)] = k
    return districts, khoroos


def seed_all(db: Session) -> None:
    print("[Холбоос] Демо өгөгдөл үүсгэж байна...")
    rng = random.Random(2026)
    now = utcnow()
    districts, khoroos = _seed_geo(db)
    pw = hash_password(settings.demo_password)

    db.add(User(full_name=ADMIN["name"], email=ADMIN["email"], password_hash=pw, role="admin",
                created_at=now - timedelta(days=120)))

    mp_users, khoroo_mp, district_mp = {}, {}, {}
    for spec in MPS:
        user = User(full_name=spec["name"], email=spec["email"], password_hash=hash_password(settings.demo_password),
                    role="mp", district_id=districts[spec["district"]].id, phone="7011" + str(rng.randint(1000, 9999)),
                    created_at=now - timedelta(days=110))
        profile = MPProfile(constituency=spec["constituency"], district_id=districts[spec["district"]].id,
                            position=spec["position"], bio=spec["bio"], focus_categories=",".join(spec["focus"]))
        profile.khoroos = [khoroos[(spec["district"], n)] for n in spec["khoroos"]]
        user.mp_profile = profile
        db.add(user)
        mp_users[spec["email"]] = user
        for n in spec["khoroos"]:
            khoroo_mp.setdefault((spec["district"], n), user)
        district_mp.setdefault(spec["district"], user)

    citizens = {}
    for email, name, dname, knum, phone in CITIZENS:
        u = User(full_name=name, email=email, password_hash=hash_password(settings.demo_password), role="citizen",
                 phone=phone, district_id=districts[dname].id, khoroo_id=khoroos[(dname, knum)].id,
                 created_at=now - timedelta(days=rng.randint(40, 100)))
        db.add(u)
        citizens[email] = u

    # Олон дэмжигч иргэд (нэвтрэх боломжгүй санамсаргүй нууц үгтэй "чимээгүй" бүртгэлүүд)
    silent_hash = hash_password(__import__("secrets").token_urlsafe(24))
    bulk = []
    dnames = [d[0] for d in DISTRICTS[:7]]
    for i in range(1, 121):
        dname = rng.choice(dnames)
        d = districts[dname]
        u = User(full_name=f"{rng.choice(FATHER_INITIALS)}.{rng.choice(GIVEN_NAMES)}",
                 email=f"irgen{i:03d}@demo.holboos.mn", password_hash=silent_hash, role="citizen",
                 district_id=d.id, khoroo_id=rng.choice(d.khoroos).id,
                 created_at=now - timedelta(days=rng.randint(5, 100)))
        db.add(u)
        bulk.append(u)
    db.flush()

    named = list(citizens.values())
    all_citizens = named + bulk
    seed_dir = settings.upload_dir / "seed"

    for idx, spec in enumerate(ISSUES, start=1):
        d = districts[spec["d"]]
        k = khoroos[(spec["d"], spec["k"])]
        author = citizens.get(spec.get("author")) or rng.choice([c for c in named if c.district_id == d.id] or named)
        mp = khoroo_mp.get((spec["d"], spec["k"])) or district_mp.get(spec["d"])
        created = now - timedelta(days=spec["days"], hours=rng.randint(0, 10), minutes=rng.randint(0, 59))
        issue = Issue(title=spec["title"], description=spec["desc"], category=spec["cat"], district_id=d.id,
                      khoroo_id=k.id, location=spec["loc"], urgency=spec["urg"], affected_scope=spec["scope"],
                      status="NEW", author_id=author.id, mp_id=mp.id if mp else None,
                      lat=round(k.lat + rng.uniform(-0.004, 0.004), 5),
                      lng=round(k.lng + rng.uniform(-0.006, 0.006), 5),
                      created_at=created, updated_at=created)
        db.add(issue)
        db.flush()

        before_rel = f"uploads/seed/issue_{idx}_before.jpg"
        generate_image(spec["cat"], True, 1000 + idx, seed_dir / f"issue_{idx}_before.jpg")
        db.add(IssueImage(issue_id=issue.id, path=before_rel, kind="original", uploaded_by_id=author.id,
                          created_at=created))
        db.add(IssueStatusHistory(issue_id=issue.id, old_status=None, new_status="NEW", changed_by_id=author.id,
                                  note="Иргэн асуудлыг мэдээллээ", created_at=created))

        # Төлөвийн явц: үе шат бүрийг цаг хугацааны дарааллаар тараана
        target = STATUSES.index(spec["status"])
        span = (now - created).total_seconds()
        step_times = [created + timedelta(seconds=span * (i / (target + 1.3)) * rng.uniform(0.85, 1.0))
                      for i in range(1, target + 1)]
        org = spec.get("org")
        for i, when in enumerate(step_times, start=1):
            status = STATUSES[i]
            if status == "RECEIVED":
                note = "Асуудлыг хүлээн авлаа"
                db.add(OfficialResponse(issue_id=issue.id, author_id=mp.id, kind="response",
                                        content=rng.choice(RECEIVED_TEXT), created_at=when))
            elif status == "UNDER_REVIEW":
                note = "Газар дээр нь шалгаж байна"
                db.add(OfficialResponse(issue_id=issue.id, author_id=mp.id, kind="update",
                                        content=rng.choice(REVIEW_TEXT), created_at=when))
            elif status == "FORWARDED":
                note = f"Хүлээн авсан байгууллага: {org}"
                issue.forwarded_to = org
                db.add(OfficialResponse(issue_id=issue.id, author_id=mp.id, kind="forward", organization=org,
                                        content="Тус асуудлыг хүлээн авч, холбогдох байгууллагад албан бичгээр "
                                                f"хүргүүлэн ажиллаж байна. Хүлээн авсан байгууллага: {org}.",
                                        created_at=when))
            elif status == "IN_PROGRESS":
                note = "Засварын ажил эхэлсэн"
                db.add(OfficialResponse(issue_id=issue.id, author_id=mp.id, kind="update",
                                        content=IN_PROGRESS_TEXT.format(org=org or "Хариуцсан байгууллага"),
                                        created_at=when))
            else:  # RESOLVED
                note = "Асуудал шийдвэрлэгдлээ"
                res = spec["resolution"]
                db.add(Resolution(issue_id=issue.id, explanation=res["explanation"], action_taken=res["action"],
                                  resolved_on=(when + timedelta(hours=8)).date(), official_response=res["response"],
                                  resolved_by_id=mp.id, created_at=when))
                db.add(OfficialResponse(issue_id=issue.id, author_id=mp.id, kind="resolution",
                                        content=res["response"], created_at=when))
                generate_image(spec["cat"], False, 2000 + idx, seed_dir / f"issue_{idx}_after.jpg")
                db.add(IssueImage(issue_id=issue.id, path=f"uploads/seed/issue_{idx}_after.jpg", kind="after",
                                  uploaded_by_id=mp.id, created_at=when))
            db.add(IssueStatusHistory(issue_id=issue.id, old_status=STATUSES[i - 1], new_status=status,
                                      changed_by_id=mp.id, note=note, created_at=when))
            issue.status = status
            issue.updated_at = when
            if status == "RECEIVED":
                issue.received_at = when
            if status == "RESOLVED":
                issue.resolved_at = when

        # Дэмжлэг (зохиогч өөрөө эхний дэмжигч)
        pool = [c for c in all_citizens if c.id != author.id]
        supporters = [author] + rng.sample(pool, min(len(pool), spec["sup"] - 1))
        for s in supporters:
            when = created + timedelta(seconds=rng.uniform(0, max(60, (now - created).total_seconds() * 0.9)))
            db.add(Support(issue_id=issue.id, user_id=s.id, created_at=when if s is not author else created))

        # Сэтгэгдэл
        texts = CATEGORY_COMMENTS.get(spec["cat"], []) + GENERIC_COMMENTS
        if target >= 1:
            texts += PROGRESS_COMMENTS
        rng.shuffle(texts)
        commenters = [c for c in named if c.id != author.id]
        for j in range(spec.get("ncom", 3)):
            when = created + timedelta(seconds=(now - created).total_seconds() * rng.uniform(0.05, 0.95))
            db.add(Comment(issue_id=issue.id, user_id=rng.choice(commenters).id, content=texts[j % len(texts)],
                           created_at=when))

        # Шийдвэрлэлтийн баталгаажуулалт
        if spec["status"] == "RESOLVED":
            voters = [s for s in supporters if s is not author]
            rng.shuffle(voters)
            yes_n, no_n = spec.get("confirm_yes", 3), spec.get("confirm_no", 0)
            base = issue.resolved_at or now
            for v in voters[:yes_n]:
                db.add(ResolutionConfirmation(issue_id=issue.id, user_id=v.id, is_resolved=True,
                                              created_at=base + timedelta(hours=rng.randint(2, 60))))
            for n, v in enumerate(voters[yes_n:yes_n + no_n]):
                db.add(ResolutionConfirmation(issue_id=issue.id, user_id=v.id, is_resolved=False,
                                              reason=DISPUTE_REASONS[n % len(DISPUTE_REASONS)],
                                              created_at=base + timedelta(hours=rng.randint(5, 70))))
            if spec.get("dispute"):
                db.add(ResolutionConfirmation(issue_id=issue.id, user_id=author.id, is_resolved=False,
                                              reason="Нэг удаа ачаад дахиад л ирэхгүй байна. Хуваарь мөрдөгдөхгүй байна.",
                                              created_at=base + timedelta(hours=30)))
            elif spec.get("author_confirms", True):
                db.add(ResolutionConfirmation(issue_id=issue.id, user_id=author.id, is_resolved=True,
                                              created_at=base + timedelta(hours=6)))
        db.flush()
        issue.support_count = len(supporters)
        issue.comment_count = spec.get("ncom", 3)
        issue.priority_score = compute_priority(issue, now)

    db.flush()
    _seed_notifications(db, citizens, mp_users)
    db.commit()
    ensure_demo_images()
    print(f"[Холбоос] Бэлэн: {len(ISSUES)} асуудал, {len(all_citizens)} иргэн, {len(MPS)} гишүүн.")


def _seed_notifications(db: Session, citizens: dict, mp_users: dict) -> None:
    def issue_by_title(prefix):
        return db.scalar(select(Issue).where(Issue.title.startswith(prefix)))

    now = utcnow()
    sar = citizens["citizen@holboos.mn"]
    garbage = issue_by_title("26-р хорооны хогийн цэг")
    busstop = issue_by_title("Автобусны буудлын")
    playground = issue_by_title("3-р хорооны тоглоомын")
    air = issue_by_title("20-р хорооны гэр хорооллын утаа")
    lighting = issue_by_title("4-р хорооны гудамжны гэрэлтүүлэг")
    items = [
        (sar, busstop, "resolved", f"🎉 Таны \"{busstop.title}\" асуудал шийдвэрлэгдлээ. "
                                   "Бодитоор шийдэгдсэн эсэхийг баталгаажуулна уу.", False, 20),
        (sar, garbage, "support", f"Таны \"{garbage.title}\" асуудлыг {garbage.support_count} иргэн дэмжиж байна.",
         False, 3),
        (sar, garbage, "comment", f"Б.Болд таны \"{garbage.title}\" асуудалд сэтгэгдэл үлдээлээ.", False, 5),
        (sar, playground, "status", f"\"{playground.title}\" асуудлын төлөв: Шийдвэрлэж байна.", True, 60),
        (sar, playground, "received", f"УИХ-ын гишүүн Г.Бат-Эрдэнэ таны \"{playground.title}\" асуудлыг хүлээн авлаа.",
         True, 400),
    ]
    mp = mp_users["mp@holboos.mn"]
    items += [
        (mp, garbage, "high_priority", f"Таны тойрогт өндөр ач холбогдолтой шинэ асуудал: \"{garbage.title}\" "
                                       f"({garbage.priority_score}/100).", False, 40),
        (mp, air, "high_support", f"Таны тойргийн \"{air.title}\" асуудал 25+ иргэний дэмжлэг авлаа.", False, 90),
        (mp, lighting, "comment", f"Иргэн Н.Цэцэгмаа \"{lighting.title}\" асуудалд сэтгэгдэл бичлээ.", False, 150),
    ]
    for user, issue, kind, message, read, minutes_ago in items:
        db.add(Notification(user_id=user.id, issue_id=issue.id, kind=kind, message=message[:300], is_read=read,
                            created_at=now - timedelta(minutes=minutes_ago)))


def ensure_demo_images() -> None:
    """Демо үзүүлэхэд иргэн/гишүүний оруулах жишээ зургууд (demo_images/ хавтас)."""
    out = settings.demo_images_dir
    files = {
        "01_zam_evdrel_umnu.jpg": ("road", True, 7),
        "02_zam_zasvarlasan_daraa.jpg": ("road", False, 7),
        "03_hog_umnu.jpg": ("garbage", True, 11),
        "04_hog_daraa.jpg": ("garbage", False, 11),
        "05_gerel_umnu.jpg": ("lighting", True, 13),
        "06_gerel_daraa.jpg": ("lighting", False, 13),
    }
    for name, (cat, before, seed) in files.items():
        path = out / name
        if not path.exists():
            generate_image(cat, before, seed, path)


def reset_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(settings.upload_dir / "seed", ignore_errors=True)
    with SessionLocal() as db:
        seed_all(db)


def seed_if_empty() -> bool:
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            return False
        seed_all(db)
        return True


if __name__ == "__main__":
    import app.models  # noqa: F401  (бүх хүснэгтийг бүртгэнэ)
    if "--reset" in sys.argv:
        reset_database()
    else:
        Base.metadata.create_all(engine)
        if not seed_if_empty():
            print("Өгөгдлийн санд өгөгдөл байна. Дахин үүсгэх бол: python -m app.seed --reset")
