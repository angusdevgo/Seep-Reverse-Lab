# Shared parsers for master-route route-scope.md.
# Line-anchored so a hint containing "primary: R11" cannot steal the real PRIMARY.
function Get-ReverseRouteScopeFields {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )
    $id = $null
    $skill = $null
    $idHits = [regex]::Matches($Text, '(?m)^- primary:\s*(\S+)\s*$')
    if ($idHits.Count -gt 0) { $id = $idHits[$idHits.Count - 1].Groups[1].Value }
    $skillHits = [regex]::Matches($Text, '(?m)^- primary_skill:\s*skills/(\S+)\s*$')
    if ($skillHits.Count -gt 0) { $skill = $skillHits[$skillHits.Count - 1].Groups[1].Value }
    return [pscustomobject]@{
        Id    = $id
        Skill = $skill
    }
}
