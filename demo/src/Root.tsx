import "./index.css";
import { Composition } from "remotion";
import { LinearDemo } from "./LinearDemo";
import { TOTAL_FRAMES } from "./scenes";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="LinearDemo"
        component={LinearDemo}
        durationInFrames={TOTAL_FRAMES}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
