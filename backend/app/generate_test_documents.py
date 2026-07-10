def generate_signed_offer_letter_jade(name="Rohan Gupta", grade="L3", location="Pune"):
    size = (900, 700)
    img, draw = new_canvas(size)
    title_font, label_font = get_font(28), get_font(22)

    draw.text((40, 30), "JADE GLOBAL", fill=TEXT_COLOR, font=title_font)
    draw.text((40, 70), "OFFER LETTER", fill=TEXT_COLOR, font=label_font)

    draw.text((40, 140), f"Name: {name}", fill=TEXT_COLOR, font=label_font)
    draw.text((40, 180), f"Grade: {grade}", fill=TEXT_COLOR, font=label_font)
    draw.text((40, 220), f"Location: {location}", fill=TEXT_COLOR, font=label_font)

    draw.text((40, 280), "CTC Structure:", fill=TEXT_COLOR, font=label_font)
    draw.text((40, 310), "[Digitally Signed]", fill=(0, 128, 0), font=label_font)

    draw.text((40, 370), "Joining Bonus: Applicable", fill=TEXT_COLOR, font=label_font)
    draw.text((40, 400), "[Digitally Signed]", fill=(0, 128, 0), font=label_font)

    watermark(draw, size)
    save_both(img, "signed_offer_letter_jade")