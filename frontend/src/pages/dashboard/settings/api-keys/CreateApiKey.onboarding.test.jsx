import { describe, expect, it, vi } from "vitest";
import { render, screen } from "src/utils/test-utils";

import CreateApiKey from "./CreateApiKey";

vi.mock("@tanstack/react-query", () => ({
  useMutation: () => ({
    data: null,
    isPending: false,
    mutate: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock("src/utils/axios", () => ({
  default: {
    post: vi.fn(),
  },
  endpoints: {
    keys: {
      generateSecretKey: "/accounts/key/generate_secret_key/",
    },
  },
}));

vi.mock("src/components/iconify", () => ({
  default: (props) => <span data-testid="iconify" {...props} />,
}));

vi.mock("src/components/svg-color", () => ({
  default: (props) => <span data-testid="svg-color" {...props} />,
}));

vi.mock("notistack", () => ({
  enqueueSnackbar: vi.fn(),
}));

vi.mock("src/utils/utils", () => ({
  copyToClipboard: vi.fn(),
}));

describe("CreateApiKey onboarding defaults", () => {
  it("prefills the key name from the onboarding handoff", () => {
    render(
      <CreateApiKey
        initialKeyName="Observe first trace"
        onClose={vi.fn()}
        open
        refreshGrid={vi.fn()}
      />,
    );

    expect(screen.getByRole("textbox")).toHaveValue("Observe first trace");
    expect(screen.getByRole("button", { name: /next/i })).toBeEnabled();
  });

  it("keeps the normal create dialog blank without an onboarding default", () => {
    render(<CreateApiKey onClose={vi.fn()} open refreshGrid={vi.fn()} />);

    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
  });
});
