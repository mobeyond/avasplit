import cv2
import os
import numpy as np
import tkinter as tk
from tkinter import filedialog
from PIL import Image

# File and Image Handling Functions
def select_input_image():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        initialdir="./in/",
        title="Select Input Image",
        filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff")]
    )
    return file_path

def save_image(output_dir, filename, image):
    if image is None or image.size == 0:
        print(f"Warning: Attempted to save empty image: {filename}")
        return
    try:
        cv2.imwrite(os.path.join(output_dir, filename), image)
    except Exception as e:
        print(f"Error saving image {filename}: {str(e)}")

# Shape Analysis Functions
def circularity(contour):
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    return 4 * np.pi * area / (perimeter * perimeter) if perimeter else 0

def is_valid_contour(contour):
    return len(contour) >= 3 and cv2.contourArea(contour) > 0

def shape_factor(contour):
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    return (4 * np.pi * area) / (perimeter * perimeter) if perimeter else 0

# Contour Processing Functions
def refined_cluster_contours(contours, image_shape, output_dir):
    total_area = image_shape[0] * image_shape[1]
    min_area = total_area * 0.001
    filtered_contours = [c for c in contours if is_valid_contour(c) and cv2.contourArea(c) >= min_area]

    if len(filtered_contours) < 2:
        print("Not enough large contours for clustering.")
        return filtered_contours, None

    features = np.float32([[shape_factor(c), cv2.contourArea(c) / total_area] for c in filtered_contours])
    features = (features - np.mean(features, axis=0)) / np.std(features, axis=0)

    n_clusters = min(4, len(filtered_contours))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels, _ = cv2.kmeans(features, n_clusters, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    cluster_image = np.zeros(image_shape[:2] + (3,), dtype=np.uint8)
    colors = [(np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255)) for _ in range(n_clusters)]
    
    for contour, label in zip(filtered_contours, labels.ravel()):
        color = colors[label]
        cv2.drawContours(cluster_image, [contour], 0, color, 2)
        M = cv2.moments(contour)
        if M["m00"] != 0:
            cX, cY = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
            cv2.circle(cluster_image, (cX, cY), 5, color, -1)

    save_image(output_dir, '5b_cluster_visualization.jpg', cluster_image)

    cluster_metrics = []
    for i in range(n_clusters):
        cluster_contours = [filtered_contours[j] for j, label in enumerate(labels.ravel()) if label == i]
        total_cluster_area = sum(cv2.contourArea(c) for c in cluster_contours)
        avg_shape_factor = np.mean([shape_factor(c) for c in cluster_contours])
        cluster_metrics.append((i, total_cluster_area, avg_shape_factor))

    best_cluster = sorted(cluster_metrics, key=lambda x: x[1], reverse=True)[0]
    shape_type = "circle" if abs(best_cluster[2] - 1) < abs(best_cluster[2] - 0.785) else "square"
    print(f"Shape type: {shape_type}", best_cluster[2])
    best_cluster_contours = [filtered_contours[i] for i, label in enumerate(labels.ravel()) if label == best_cluster[0]]

    best_cluster_image = np.zeros(image_shape[:2] + (3,), dtype=np.uint8)
    cv2.drawContours(best_cluster_image, best_cluster_contours, -1, (0, 255, 0), 2)
    for contour in best_cluster_contours:
        M = cv2.moments(contour)
        if M["m00"] != 0:
            cX, cY = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
            cv2.circle(best_cluster_image, (cX, cY), 5, (0, 0, 255), -1)
    
    save_image(output_dir, '5c_best_cluster.jpg', best_cluster_image)

    return best_cluster_contours, shape_type

def create_adaptive_template(contours, shape_type):
    if not contours:
        raise ValueError("No contours provided to create template.")

    avg_area = np.mean([cv2.contourArea(c) for c in contours])

    if shape_type == "circle":
        radius = int(np.sqrt(avg_area / np.pi))
        center_x = int(np.mean([c[:, 0, 0].mean() for c in contours]))
        center_y = int(np.mean([c[:, 0, 1].mean() for c in contours]))
        return (center_x, center_y, radius)
    else:  # square
        side = int(np.sqrt(avg_area))
        center_x = int(np.mean([c[:, 0, 0].mean() for c in contours]))
        center_y = int(np.mean([c[:, 0, 1].mean() for c in contours]))
        return (center_x - side // 2, center_y - side // 2, side, side)

def match_template_to_cluster(cluster, template, image_shape, shape_type):
    matched_contours = []
    excluded_areas = np.zeros(image_shape[:2], dtype=np.uint8)
    
    for contour in cluster:
        if not is_valid_contour(contour):
            continue
        mask = np.zeros(image_shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [contour], 0, 1, -1)
        if cv2.countNonZero(cv2.bitwise_and(excluded_areas, mask)) == 0:
            matched_contours.append(contour)
            excluded_areas = cv2.bitwise_or(excluded_areas, mask)
    
    return matched_contours

def make_more_circular(contour):
    if len(contour) < 5:
        return contour
    ellipse = cv2.fitEllipse(contour)
    (x, y), (MA, ma), angle = ellipse
    radius = int(max(MA, ma) / 2)
    return np.array([[[int(x + radius * np.cos(np.deg2rad(i))), 
                       int(y + radius * np.sin(np.deg2rad(i)))]] for i in range(360)], dtype=np.int32)

def make_more_square(contour):
    if len(contour) < 4:
        return contour
    rect = cv2.minAreaRect(contour)
    box = np.int32(cv2.boxPoints(rect))
    return np.array([box], dtype=np.int32)

def filter_shapes_by_size(shapes, template, image_shape, shape_type):
    template_area = np.pi * template[2]**2 if shape_type == "circle" else template[2] * template[3]
    filtered_shapes = [s for s in shapes if 0.5 * template_area <= cv2.contourArea(s) <= 1.5 * template_area]
    
    to_remove = set()
    for i, shape1 in enumerate(filtered_shapes):
        if i in to_remove:
            continue
        for j, shape2 in enumerate(filtered_shapes[i+1:], start=i+1):
            if j in to_remove:
                continue
            overlap = calculate_overlap(shape1, shape2, image_shape)
            if overlap > 0.2:
                area1, area2 = cv2.contourArea(shape1), cv2.contourArea(shape2)
                to_remove.add(j if abs(area1 - template_area) <= abs(area2 - template_area) else i)
                if i in to_remove:
                    break
    
    return [s for i, s in enumerate(filtered_shapes) if i not in to_remove]

def generate_profile_regions(filtered_shapes, image_shape):
    profile_regions = []
    excluded_areas = np.zeros(image_shape[:2], dtype=np.uint8)
    
    for shape in filtered_shapes:
        mask = np.zeros(image_shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [shape], 0, 1, -1)
        if cv2.countNonZero(cv2.bitwise_and(excluded_areas, mask)) == 0:
            x, y, w, h = cv2.boundingRect(shape)
            profile_regions.append((int(x), int(y), int(w), int(h)))
            excluded_areas = cv2.bitwise_or(excluded_areas, mask)
    
    return profile_regions

def extract_profiles(image, regions, output_dir):
    profile_images = []
    for i, (x, y, w, h) in enumerate(regions):
        profile = image[y:y+h, x:x+w]
        if profile is not None and profile.size > 0:
            profile_images.append(profile)
    
    final_image = image.copy()
    for i, (x, y, w, h) in enumerate(regions):
        cv2.rectangle(final_image, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(final_image, f'{i+1}', (x, y-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 0), 1, cv2.LINE_AA)
    save_image(output_dir, '5_final_profiles.jpg', final_image)
    
    return profile_images

def draw_contours(image_shape, contours):
    if not contours:
        return None
    image = np.zeros(image_shape[:2], dtype=np.uint8)
    cv2.drawContours(image, contours, -1, 255, 2)
    return image

def calculate_overlap(contour1, contour2, image_shape):
    mask1 = np.zeros(image_shape[:2], dtype=np.uint8)
    mask2 = np.zeros(image_shape[:2], dtype=np.uint8)
    cv2.drawContours(mask1, [contour1], 0, 1, -1)
    cv2.drawContours(mask2, [contour2], 0, 1, -1)
    intersection = cv2.bitwise_and(mask1, mask2)
    union = cv2.bitwise_or(mask1, mask2)
    return np.sum(intersection) / np.sum(union)

# Image Processing Pipeline
def preprocess_image(image_path):
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 1)    
    return image, gray, blurred

def detect_edges_and_contours(blurred):
    edges = cv2.Canny(blurred, 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print("Number of contours detected:", len(contours))
    
    enclosing_circles = [cv2.minEnclosingCircle(contour) for contour in contours]
    return edges, contours, enclosing_circles

def process_contours(contours, enclosing_circles, image_shape, output_dir):
    valid_contours = [contour for contour, ((_, _), radius) in zip(contours, enclosing_circles) if radius >= 10]
    
    valid_contours, shape_type = refined_cluster_contours(valid_contours, image_shape, output_dir)
    if not valid_contours:
        print("No valid contours found after refinement.")
        return [], None, None

    template = create_adaptive_template(valid_contours, shape_type)
    matched_contours = match_template_to_cluster(contours, template, image_shape, shape_type)
    
    processed_group = [make_more_circular(c) if shape_type == "circle" else make_more_square(c) 
                       for c in matched_contours if is_valid_contour(c)]
    
    filtered_shapes = filter_shapes_by_size(processed_group, template, image_shape, shape_type)
    profile_regions = generate_profile_regions(filtered_shapes, image_shape)
    
    save_image(output_dir, '10_filtered_shapes.jpg', draw_contours(image_shape, filtered_shapes))
    
    return profile_regions, template, shape_type

def create_gif_from_profiles(profiles, output_dir, gif_duration=500):
    if not profiles:
        print("No profiles to create GIF from.")
        return

    for i in range(0, len(profiles), 25):
        gif_profiles = profiles[i:i+25]
        gif_count = i // 25 + 1
        
        pil_images = [Image.fromarray(cv2.cvtColor(profile, cv2.COLOR_BGR2RGB)) for profile in gif_profiles]
        
        gif_path = os.path.join(output_dir, f'profiles_gif_{gif_count}.gif')
        pil_images[0].save(
            gif_path,
            save_all=True,
            append_images=pil_images[1:],
            duration=gif_duration,
            loop=0
        )
        print(f"Created GIF: {gif_path}")

def detect_and_extract_profiles(image_path, output_dir):
    image, gray, blurred = preprocess_image(image_path)
    edges, contours, enclosing_circles = detect_edges_and_contours(blurred)
    
    profile_regions, template, shape_type = process_contours(contours, enclosing_circles, image.shape[:2], output_dir)
    
    if not profile_regions:
        print("No profile regions detected.")
        return [], len(contours), 0

    profile_images = extract_profiles(image, profile_regions, output_dir)
    create_gif_from_profiles(profile_images, output_dir)
    
    return profile_images, len(contours), len(profile_regions)

# Main Execution
def main():
    input_image = select_input_image()
    if not input_image:
        print("No image selected. Exiting.")
        return

    output_dir = os.path.join(os.path.dirname(input_image), "output")
    os.makedirs(output_dir, exist_ok=True)

    profiles, total_contours, extracted_profiles = detect_and_extract_profiles(input_image, output_dir)

    print(f"Total contours detected: {total_contours}")
    print(f"Profiles extracted: {extracted_profiles}")

if __name__ == "__main__":
    main()
