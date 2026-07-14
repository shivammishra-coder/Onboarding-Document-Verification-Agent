import os
from PIL import Image, ImageDraw, ImageFont

def get_font(size, bold=False):
    """Attempt to load standard fonts. Fallbacks to default if missing."""
    font_name = "arialbd.ttf" if bold else "arial.ttf"
    mac_font = "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf"
    try:
        return ImageFont.truetype(font_name, size)
    except IOError:
        try:
            return ImageFont.truetype(mac_font, size)
        except IOError:
            return ImageFont.load_default()

def generate_exact_pan(output_path):
    # Canvas dimensions and background color matching the image
    width, height = 750, 420
    bg_color = "#e1f1f9"  # Light blue matching the reference
    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # 1. Header Section (White background)
    draw.rectangle([(0, 0), (width, 70)], fill="white")
    draw.line([(0, 70), (width, 70)], fill="black", width=1)
    
    # Header Text
    font_header_main = get_font(20, bold=True)
    font_header_sub = get_font(16, bold=True)
    draw.text((375, 15), "INCOME TAX DEPARTMENT", fill="black", font=font_header_main, anchor="mt")
    draw.text((375, 42), "GOVT. OF INDIA", fill="black", font=font_header_sub, anchor="mt")

    # 2. Left Column (Photo & Signature)
    # Photo Box
    draw.rectangle([(40, 95), (170, 240)], fill="#e0e0e0", outline="black", width=1)
    draw.text((105, 167), "PHOTO", fill="#555", font=get_font(14, bold=True), anchor="mm")
    
    # Signature Box
    draw.rectangle([(40, 255), (190, 310)], fill="white", outline="black", width=1)
    draw.text((115, 282), "SIGNATURE", fill="#ccc", font=get_font(12, bold=True), anchor="mm")

    # 3. Middle Column (Details)
    x_details = 210
    font_label = get_font(12)
    font_value = get_font(18, bold=True)
    
    # Name
    draw.text((x_details, 95), "Name / ", fill="black", font=font_label)
    draw.text((x_details, 115), "Rohan Gupta", fill="black", font=font_value) # Corrected Name
    
    # Father's Name
    draw.text((x_details, 155), "Father's Name /   ", fill="black", font=font_label)
    draw.text((x_details, 175), "Suresh Gupta", fill="black", font=font_value)
    
    # Date of Birth
    draw.text((x_details, 215), "Date of Birth /   ", fill="black", font=font_label)
    draw.text((x_details, 235), "15-07-1993", fill="black", font=font_value)

    # 4. Right Column (QR & PAN Box)
    # QR Code Placeholder Box
    qr_x, qr_y = 560, 95
    qr_size = 110
    draw.rectangle([(qr_x, qr_y), (qr_x + qr_size, qr_y + qr_size)], fill="white", outline="black", width=2)
    # Draw QR Finder Patterns (The 3 inner squares)
    for offset_x, offset_y in [(5, 5), (qr_size-20, 5), (5, qr_size-20)]:
        draw.rectangle([(qr_x + offset_x, qr_y + offset_y), (qr_x + offset_x + 15, qr_y + offset_y + 15)], fill="black")
        draw.rectangle([(qr_x + offset_x + 4, qr_y + offset_y + 4), (qr_x + offset_x + 11, qr_y + offset_y + 11)], fill="white")
    draw.text((qr_x + qr_size//2, qr_y + qr_size//2), "QR CODE", fill="black", font=get_font(12), anchor="mm")

    # PAN Number Box
    pan_box_x, pan_box_y = 370, 265
    pan_box_w, pan_box_h = 350, 75
    draw.rectangle([(pan_box_x, pan_box_y), (pan_box_x + pan_box_w, pan_box_y + pan_box_h)], fill="white", outline="black", width=1)
    
    draw.text((pan_box_x + 10, pan_box_y + 10), "Permanent Account Number Card", fill="black", font=get_font(12))
    
    # Massive PAN text
    draw.text((pan_box_x + pan_box_w//2, pan_box_y + 45), "ABCDE1234F", fill="black", font=get_font(32, bold=True), anchor="mm")

    # Add a thin outer border to the entire image
    draw.rectangle([(0, 0), (width-1, height-1)], outline="black", width=1)

    # Save the output
    img.save(output_path)
    print(f"Image successfully generated and saved to: {output_path}")

if __name__ == "__main__":
    output_directory = "onboarding_docs"
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        
    generate_exact_pan(os.path.join(output_directory, "exact_pan_rohan_gupta.png"))