from a2a.types import SendMessageRequest, SendMessageConfiguration

print("SendMessageRequest fields:")
for f in SendMessageRequest.DESCRIPTOR.fields:
    print(" ", f.name)

try:
    from a2a.types import SendMessageConfiguration
    print("\nSendMessageConfiguration fields:")
    for f in SendMessageConfiguration.DESCRIPTOR.fields:
        print(" ", f.name)
except Exception as e:
    print("SendMessageConfiguration not found:", e)

print("\nStreamResponse fields:")
from a2a.types import StreamResponse
for f in StreamResponse.DESCRIPTOR.fields:
    print(" ", f.name)