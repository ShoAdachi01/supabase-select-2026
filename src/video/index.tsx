import { Composition, registerRoot } from 'remotion';
import { LaunchShot, type ShotProps } from './LaunchShot';

const defaults: ShotProps = {
  preset: 'reveal',
  theme: 'paper',
  headline: 'Your product. In motion.',
  subtitle: '',
  product: '',
  details: [],
  frames: 90,
};
function Root() {
  return (
    <Composition
      id="LaunchShot"
      component={LaunchShot}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={90}
      defaultProps={defaults}
      calculateMetadata={({ props }) => ({ durationInFrames: props.frames })}
    />
  );
}
registerRoot(Root);
