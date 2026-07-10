# test_ocr_pdf.py
import fitz
from PIL import Image
import io
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\shivam.mishra_jadegl\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

doc = fitz.open("../test_documents/aadhaar_card.pdf")
page = doc.load_page(0)
pix = page.get_pixmap(dpi=300)
image = Image.open(io.BytesIO(pix.tobytes("png")))
print(pytesseract.image_to_string(image))
doc.close()