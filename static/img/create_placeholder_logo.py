from PIL import Image, ImageDraw, ImageFont

def create_placeholder_logo():
    # Create a new image with a dark background
    width, height = 200, 80
    image = Image.new('RGBA', (width, height), (28, 33, 41, 255))
    draw = ImageDraw.Draw(image)
    
    # Add text
    text = "CAC"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except:
        font = ImageFont.load_default()
    
    # Get text size
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # Calculate text position for centering
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    # Draw text in white
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
    
    # Save the image
    image.save('static/img/placeholder-logo.png')

if __name__ == "__main__":
    create_placeholder_logo()
