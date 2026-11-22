"""Camera check, 30 s. Switch the phone server off and on once to test reconnect."""
import time

from camera import Camera


def main():
    cam = Camera()
    try:
        start = last = time.monotonic()
        count, ages, shape = 0, [], None
        while time.monotonic() - start < 30:
            frame, age = cam.read(timeout=0.05)
            if frame is not None:
                count += 1
                ages.append(age)
                shape = frame.shape
            now = time.monotonic()
            if now - last >= 1.0:
                avg = 1000 * sum(ages) / len(ages) if ages else 0.0
                print("%5.1f FPS | wait in board %4.1f ms | shape %s" % (count / (now - last), avg, shape))
                count, ages, last = 0, [], now
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()
    print("done")


if __name__ == "__main__":
    main()
