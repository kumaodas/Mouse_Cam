"""
Unit tests for Hand domain entity.
"""

from gesture_mouse.domain.models import Hand, NormalizedPoint, HandLandmarkId, Handedness


def test_hand_model_landmarks_access():
    landmarks = {
        HandLandmarkId.WRIST: NormalizedPoint(0.5, 0.8),
        HandLandmarkId.THUMB_TIP: NormalizedPoint(0.4, 0.5),
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.5, 0.3),
        HandLandmarkId.INDEX_FINGER_PIP: NormalizedPoint(0.5, 0.5),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.6, 0.3),
        HandLandmarkId.MIDDLE_FINGER_PIP: NormalizedPoint(0.6, 0.5),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.7, 0.7),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.7, 0.6),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.8, 0.7),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.8, 0.6),
    }

    hand = Hand(landmarks=landmarks, handedness=Handedness.RIGHT)

    assert hand.wrist == NormalizedPoint(0.5, 0.8)
    assert hand.thumb_tip == NormalizedPoint(0.4, 0.5)
    assert hand.index_tip == NormalizedPoint(0.5, 0.3)

    # In camera coordinates, tip.y < pip.y means finger points up (extended)
    assert hand.is_index_extended() is True
    assert hand.is_middle_extended() is True
    # Ring and pinky have tip.y > pip.y (curled down)
    assert hand.is_ring_extended() is False
    assert hand.is_pinky_extended() is False


def test_hand_is_near_camera_edge():
    # Normal hand in center
    lms_center = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.5, 0.3),
        HandLandmarkId.INDEX_FINGER_MCP: NormalizedPoint(0.5, 0.6),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.6, 0.3),
    }
    hand_center = Hand(landmarks=lms_center)
    assert hand_center.is_near_camera_edge(margin=0.02) is False

    # Hand pointing finger touching left border (x <= 0.015)
    lms_edge = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.01, 0.3),
        HandLandmarkId.INDEX_FINGER_MCP: NormalizedPoint(0.05, 0.6),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.10, 0.3),
    }
    hand_edge = Hand(landmarks=lms_edge)
    assert hand_edge.is_near_camera_edge(margin=0.02) is True


def test_hand_macro_poses():
    # 1. Open palm (all fingers extended: tip.y < pip.y)
    open_palm_lms = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.4, 0.2),
        HandLandmarkId.INDEX_FINGER_PIP: NormalizedPoint(0.4, 0.4),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.5, 0.2),
        HandLandmarkId.MIDDLE_FINGER_PIP: NormalizedPoint(0.5, 0.4),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.6, 0.2),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.6, 0.4),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.7, 0.2),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.7, 0.4),
    }
    hand_palm = Hand(landmarks=open_palm_lms)
    assert hand_palm.is_open_palm() is True
    assert hand_palm.is_fist() is False

    # 2. Closed fist (all fingers curled: tip.y >= pip.y)
    fist_lms = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.4, 0.5),
        HandLandmarkId.INDEX_FINGER_PIP: NormalizedPoint(0.4, 0.3),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.5, 0.5),
        HandLandmarkId.MIDDLE_FINGER_PIP: NormalizedPoint(0.5, 0.3),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.6, 0.5),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.6, 0.3),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.7, 0.5),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.7, 0.3),
    }
    hand_fist = Hand(landmarks=fist_lms)
    assert hand_fist.is_fist() is True
    assert hand_fist.is_open_palm() is False

    # 3. Peace sign (Index & Middle extended, Ring & Pinky curled)
    peace_lms = {
        HandLandmarkId.INDEX_FINGER_TIP: NormalizedPoint(0.4, 0.2),
        HandLandmarkId.INDEX_FINGER_PIP: NormalizedPoint(0.4, 0.4),
        HandLandmarkId.MIDDLE_FINGER_TIP: NormalizedPoint(0.5, 0.2),
        HandLandmarkId.MIDDLE_FINGER_PIP: NormalizedPoint(0.5, 0.4),
        HandLandmarkId.RING_FINGER_TIP: NormalizedPoint(0.6, 0.5),
        HandLandmarkId.RING_FINGER_PIP: NormalizedPoint(0.6, 0.3),
        HandLandmarkId.PINKY_TIP: NormalizedPoint(0.7, 0.5),
        HandLandmarkId.PINKY_PIP: NormalizedPoint(0.7, 0.3),
    }
    hand_peace = Hand(landmarks=peace_lms)
    assert hand_peace.is_peace_sign() is True
    assert hand_peace.is_open_palm() is False
    assert hand_peace.is_fist() is False
