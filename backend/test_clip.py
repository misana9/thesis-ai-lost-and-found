from clip_service import encode_image, encode_text, cosine_similarity

image_vec2 = encode_image("flask2.jpeg")
# point to any image file you have locally for the test
image_vec = encode_text("a black ballpen with a cap")

score = cosine_similarity(image_vec2, image_vec)
print(f"Similarity score: {score:.4f}")