import {
  AudioWaveform,
  CloudUpload,
  Download,
  FileAudio,
  FolderPlus,
  Gauge,
  HardDrive,
  History,
  ListEnd,
  Maximize,
  Music,
  Music2,
  PanelLeft,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Repeat2,
  RotateCcw,
  Settings2,
  SkipBack,
  Square,
  Trash2,
  Timer,
  Upload,
  Volume2,
  VolumeX,
  X,
  Youtube,
  createIcons,
} from "lucide";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";

const icons = {
  AudioWaveform, CloudUpload, Download, FileAudio, FolderPlus, Gauge, ListEnd,
  HardDrive, History, Maximize, Music, Music2, PanelLeft, Pause, Play, Plus, RefreshCw, Repeat2,
  RotateCcw, Settings2, SkipBack, Square, Timer, Trash2, Upload, Volume2, VolumeX, X, Youtube,
};

const renderIcons = () => createIcons({ icons });

export { RegionsPlugin, WaveSurfer, renderIcons };
