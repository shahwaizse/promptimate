-- PromptimateAutoplay (LocalScript in StarterPlayerScripts, installed by roblox_install / roblox_perform).
-- Play mode: performs every character's Promptimate chain on this client, which is what a screen recording sees.
-- Switch off with the attribute Autoplay = false on ReplicatedStorage.Promptimate; StartDelay = seconds to wait.
local RS = game:GetService("ReplicatedStorage")
local D = require(RS:WaitForChild("Promptimate"):WaitForChild("ShortDirector"))
D.autoplay()
