# Copyright 2019 Toyota Research Institute.  All rights reserved.
"""Visualization tools for a variety of tasks"""
import numpy as np
from matplotlib.cm import get_cmap

import cv2
from dgp.utils.camera import Camera

COLOR_RED = (255, 0, 0)
COLOR_GREEN = (0, 255, 0)
COLOR_BLUE = (0, 0, 255)
COLOR_GRAY = (100, 100, 100)
COLOR_DARKGRAY = (50, 50, 50)
COLOR_WHITE = (255, 255, 255)


def print_status(image, text):
    """Adds a status bar at the bottom of image, with provided text.

    Parameters
    ----------
    image: np.array of shape (H, W, 3)
        Image to print status on.

    text: str
        Text to be printed.

    Returns
    -------
    image: np.array of shape (H, W, 3)
        Image with status printed
    """
    H, W = image.shape[:2]
    status_xmax = int(W)
    status_ymin = H - 40
    text_offset = int(5 * 1)
    cv2.rectangle(image, (0, status_ymin), (status_xmax, H), COLOR_DARKGRAY, thickness=-1)
    cv2.putText(image, '%s' % text, (text_offset, H - text_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR_WHITE, thickness=1)
    return image


def mosaic(items, scale=1.0, pad=3, grid_width=None):
    """Creates a mosaic from list of images.

    Parameters
    ----------
    items: list of np.ndarray
        List of images to mosaic.

    scale: float, default=1.0
        Scale factor applied to images. scale > 1.0 enlarges images.

    pad: int, default=3
        Padding size of the images before mosaic

    grid_width: int, default=None
        Mosaic width or grid width of the mosaic

    Returns
    -------
    image: np.array of shape (H, W, 3)
        Image mosaic
    """
    # Determine tile width and height
    N = len(items)
    assert N > 0, 'No items to mosaic!'
    grid_width = grid_width if grid_width else np.ceil(np.sqrt(N)).astype(int)
    grid_height = np.ceil(N * 1. / grid_width).astype(np.int)
    input_size = items[0].shape[:2]
    target_shape = (int(input_size[1] * scale), int(input_size[0] * scale))
    mosaic_items = []
    for j in range(grid_width * grid_height):
        if j < N:
            # Only the first image is scaled, the rest are re-shaped
            # to the same size as the previous image in the mosaic
            im = cv2.resize(items[j], dsize=target_shape)
            mosaic_items.append(im)
        else:
            mosaic_items.append(np.zeros_like(mosaic_items[-1]))

    # Stack W tiles horizontally first, then vertically
    im_pad = lambda im: cv2.copyMakeBorder(im, pad, pad, pad, pad, cv2.BORDER_CONSTANT, 0)
    mosaic_items = [im_pad(im) for im in mosaic_items]
    hstack = [np.hstack(mosaic_items[j:j + grid_width]) for j in range(0, len(mosaic_items), grid_width)]
    mosaic = np.vstack(hstack) if len(hstack) > 1 \
        else hstack[0]
    return mosaic


def render_bbox2d_on_image(img, bboxes2d, colors=None, texts=None):
    """Render list of bounding box2d on image.

    Parameters
    ----------
    img: np.ndarray
        Image to render bounding boxes onto.

    bboxes2d: np.ndarray (N x 4)
        Array of 2d bounding box (x, y, w, h).

    colors: list
        List of color tuples.

    texts: list, default: None
        List of str classes.

    Returns
    -------
    img: np.array
        Image with rendered bounding boxes.
    """
    boxes = [
        np.int32([[bbox2d[0], bbox2d[1]], [bbox2d[0] + bbox2d[2], bbox2d[1]],
                  [bbox2d[0] + bbox2d[2], bbox2d[1] + bbox2d[3]], [bbox2d[0], bbox2d[1] + bbox2d[3]]])
        for bbox2d in bboxes2d
    ]
    if colors is None:
        cv2.polylines(img, boxes, True, COLOR_RED, thickness=2)
    else:
        assert len(boxes) == len(colors), 'len(boxes) != len(colors)'
        for idx, box in enumerate(boxes):
            cv2.polylines(img, [box], True, colors[idx], thickness=2)

    # Add texts
    if texts:
        assert len(boxes) == len(texts), 'len(boxes) != len(texts)'
        for idx, box in enumerate(boxes):
            cv2.putText(img, texts[idx], tuple(box[0]), cv2.FONT_HERSHEY_SIMPLEX, 1,
                        COLOR_WHITE, 2, cv2.LINE_AA)
    return img


def render_pointcloud_on_image(img, camera, Xw, colormap='jet', percentile=80):
    """Render pointcloud on image.

    Parameters
    ----------
    img: np.ndarray
        Image to render bounding boxes onto.

    camera: Camera
        Camera object with appropriately set extrinsics wrt world.

    Xw: np.ndarray (N x 3)
        3D point cloud (x, y, z) in the world coordinate.

    colormap: str, default: jet
        Colormap used for visualizing the inverse depth.

    percentile: float, default: 80
        Use this percentile to normalize the inverse depth.

    Returns
    -------
    img: np.array
        Image with rendered point cloud.
    """
    cmap = get_cmap('jet')
    # Move point cloud to the camera's (C) reference frame from the world (W)
    Xc = camera.p_cw * Xw
    # Project the points as if they were in the camera's frame of reference
    uv = Camera(K=camera.K).project(Xc)
    # Colorize the point cloud based on depth
    z_c = Xc[:, 2]
    zinv_c = 1. / (z_c + 1e-6)
    zinv_c /= np.percentile(zinv_c, percentile)
    colors = (cmap(np.clip(zinv_c, 0., 1.0))[:, :3] * 255).astype(np.uint8)

    # Create an empty image to overlay
    H, W, _ = img.shape
    vis = np.zeros_like(img)
    in_view = np.logical_and.reduce([(uv >= 0).all(axis=1), uv[:, 0] < W, uv[:, 1] < H, z_c > 0])
    uv, colors = uv[in_view].astype(int), colors[in_view]
    vis[uv[:, 1], uv[:, 0]] = colors

    # Dilate visualization so that they render clearly
    vis = cv2.dilate(vis, np.ones((5, 5)))
    return np.maximum(vis, img)


class BEVImage:
    """A class for bird's eye view visualization, which generates a canvas of bird's eye view image,
    This assumes that x-right, y-forward, so the projection will be in the first 2 coordinates 0, 1 (i.e. x-y plane)

    Parameters
    ----------
    metric_width: float, default: 100.
        Metric extent of the view in width (X)

    metric_height: float, default: 100.
        Metric extent of the view in height (Y)

    pixels_per_meter: float, default: 10.
        Scale that expresses pixels per meter

    polar_step_size_meters: int, default: 10
        Metric steps at which to draw the polar grid

    x-axis: int, default: 0
        Axis corresponding to the right of the BEV image.

    y-axis: int, default: 1
        Axis corresponding to the forward of the BEV image.
    """
    def __init__(
        self, metric_width=100., metric_height=100., pixels_per_meter=10., polar_step_size_meters=10, xaxis=0, yaxis=1
    ):
        assert xaxis != yaxis, 'Provide different x and y axis coordinates'
        self._metric_width = metric_width
        self._metric_height = metric_height
        self._pixels_per_meter = pixels_per_meter
        self._xaxis = xaxis
        self._yaxis = yaxis
        self._center_pixel = (int(metric_width * pixels_per_meter) // 2, int(metric_height * pixels_per_meter) // 2)
        self.data = np.zeros((int(metric_height * pixels_per_meter), int(metric_width * pixels_per_meter), 3),
                             dtype=np.uint8)

        # Draw metric polar grid
        for i in range(1, int(max(self._metric_width, self._metric_height)) // polar_step_size_meters):
            cv2.circle(
                self.data, self._center_pixel, int(i * polar_step_size_meters * self._pixels_per_meter), (50, 50, 50), 1
            )

    def __repr__(self):
        return 'width: {}, height: {}, data: {}'.format(self._metric_width, self._metric_height, type(self.data))

    def render_point_cloud(self, point_cloud):
        """Render point cloud in BEV perspective.

        Parameters
        ----------
        point_cloud: numpy array with shape (N, 3), default: None
            3D cloud points in the sensor coordinate frame.
        """

        # Draw point-cloud
        point_cloud2d = np.vstack([point_cloud[:, self._xaxis], point_cloud[:, self._yaxis]]).T
        point_cloud2d[:, 0] = self._center_pixel[0] + point_cloud2d[:, 0] * self._pixels_per_meter
        point_cloud2d[:, 1] = self._center_pixel[1] - point_cloud2d[:, 1] * self._pixels_per_meter
        H, W = self.data.shape[:2]
        uv = point_cloud2d.astype(np.int32)
        in_view = np.logical_and.reduce([(point_cloud2d >= 0).all(axis=1), point_cloud2d[:, 0] < W, point_cloud2d[:, 1] < H])
        uv = uv[in_view]
        self.data[uv[:, 1], uv[:, 0], :] = 128

    def render_bounding_box_3d(self, bboxes3d, color=None, texts=None):
        """Render bounding box 3d in BEV perspective.

        Parameters
        ----------
        bboxes3d: list of BoundingBox3D, default: None
            3D annotations in the sensor coordinate frame.

        color: RGB tuple, default: None
            If provided, draw boxes using this color instead of red forward/blue back

        texts: list of str, default: None
            3D annotation category name.
        """

        if color is None:
            colors = [COLOR_RED, COLOR_GREEN, COLOR_BLUE, COLOR_GRAY]
        else:
            colors = [color] * 4

        # Draw cuboids
        for bidx, bbox in enumerate(bboxes3d):
            # Do orthogonal projection and bring into pixel coordinate space
            corners = bbox.corners
            corners2d = np.vstack([corners[:, self._xaxis], corners[:, self._yaxis]]).T

            # Compute the center and offset of the corners
            corners2d[:, 0] = self._center_pixel[0] + corners2d[:, 0] * self._pixels_per_meter
            corners2d[:, 1] = self._center_pixel[1] - corners2d[:, 1] * self._pixels_per_meter
            center = np.mean(corners2d, axis=0).astype(np.int32)
            corners2d = corners2d.astype(np.int32)

            # Draw object center and green line towards front face, unless color specified
            cv2.circle(self.data, tuple(center), 1, COLOR_GREEN)
            cv2.line(self.data, tuple(center), ((corners2d[0][0] + corners2d[1][0])//2, \
                (corners2d[0][1] + corners2d[1][1]) // 2), COLOR_WHITE, 2)

            # Draw front face, side faces and back face
            cv2.line(self.data, tuple(corners2d[0]), tuple(corners2d[1]), colors[0], 2)
            cv2.line(self.data, tuple(corners2d[3]), tuple(corners2d[4]), colors[3], 2)
            cv2.line(self.data, tuple(corners2d[1]), tuple(corners2d[5]), colors[3], 2)
            cv2.line(self.data, tuple(corners2d[4]), tuple(corners2d[5]), colors[2], 2)

            if texts:
                cv2.putText(self.data, texts[bidx], tuple(corners2d[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            COLOR_WHITE, 2, cv2.LINE_AA)