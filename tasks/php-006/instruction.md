<uploaded_files>
/testbed
</uploaded_files>

I've uploaded a php code repository in the directory /testbed. Consider the following issue description:

<issue_description>
# [BUG] JsonException in SmartSerializer: Single unpaired UTF-16 surrogate in unicode escape

### What is the bug?
`SmartSerializer::decode()` throws a `JsonException` when OpenSearch returns a JSON response containing a single unpaired UTF-16 surrogate escape.
In our case this happens with search highlight responses. A field contains a non-BMP character, and the highlighter inserts `<em>` tags between the UTF-16 surrogate pair. The response then contains something like:
```json
{
  "highlight": {
    "sentence": [
      "<em>\\ud83c</em>\\udd11 some text"
    ]
  }
}
```
PHP's `json_decode(..., JSON_THROW_ON_ERROR)` fails with:
```text
Single unpaired UTF-16 surrogate in unicode escape
```
This causes the OpenSearch PHP client to throw before the application can handle the search response.

### How can one reproduce the bug?
Use `SmartSerializer` to deserialize a JSON string containing an unpaired surrogate escape:
```php
use OpenSearch\Serializers\SmartSerializer;
$serializer = new SmartSerializer();
$json = '{"highlight":{"sentence":["<em>\\ud83c</em>\\udd11 some text"]}}';
$serializer->deserialize($json, ['content-type' => ['application/json']]);
```
Actual result:
```text
OpenSearch\Exception\JsonException: Single unpaired UTF-16 surrogate in unicode escape
```

### What is the expected behavior?
The client should not fail the entire response deserialization when the response contains an unpaired UTF-16 surrogate escape.
It would be acceptable to either replace the invalid surrogate escape with the Unicode replacement character, or otherwise recover in a way that allows the response to be decoded.

Elasticsearch PHP client appears to have handled a similar issue in 7.16.0:
[https://www.elastic.co/guide/en/elasticsearch/client/php-api/8.19/release-notes.html#rn-7-16-0](https://www.elastic.co/guide/en/elasticsearch/client/php-api/8.19/release-notes.html#rn-7-16-0)
Release note:
> Fixed UTF-16 issue in SmartSerializer with single unpaired surrogate in unicode escape


### What is your host/environment?
- [redacted]-repo version: 2.5.1 / 2.6.0
- PHP version: 8.x
- OpenSearch version: 2.x

### Do you have any screenshots?
No.

### Do you have any additional context?
This can happen even when the indexed source data does not contain broken UTF-16. The source may contain a valid non-BMP character such as `🄑`, but the highlight response can split the surrogate pair by inserting markup between the two escape sequences.

For example, the original character is `🄑`, encoded in JSON as `\ud83c\udd11`.
When highlighting splits it, the response can contain:

```json
"<em>\\ud83c</em>\\udd11"
```

This makes `\ud83c` an unpaired high surrogate and causes PHP `json_decode(..., JSON_THROW_ON_ERROR)` to fail.


</issue_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the <issue_description> are met?
I've already taken care of all changes to any of the test files described in the <issue_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
Also the development php environment is already set up for you (i.e., all dependencies already installed), so you don't need to install other packages.
Your task is to make the minimal changes to non-test files in the /testbed directory to ensure the <issue_description> is satisfied.

Follow these phases to resolve the issue:

Phase 1. READING: read the problem and reword it in clearer terms
   1.1 If there are code or config snippets. Express in words any best practices or conventions in them.
   1.2 Highlight message errors, method names, variables, file names, stack traces, and technical details.
   1.3 Explain the problem in clear terms.
   1.4 Enumerate the steps to reproduce the problem.
   1.5 Highlight any best practices to take into account when testing and fixing the issue.

Phase 2. RUNNING: install and run the tests on the repository
   2.1 Follow the readme.
   2.2 Install the environment and anything needed.
   2.3 Iterate and figure out how to run the tests.

Phase 3. EXPLORATION: find the files that are related to the problem and possible solutions
   3.1 Use `grep` to search for relevant methods, classes, keywords and error messages.
   3.2 Identify all files related to the problem statement.
   3.3 Propose the methods and files to fix the issue and explain why.
   3.4 From the possible file locations, select the most likely location to fix the issue.

Phase 4. TEST CREATION: before implementing any fix, create a script to reproduce and verify the issue
   4.1 Look at existing test files in the repository to understand the test format/structure.
   4.2 Create a minimal reproduction script that reproduces the located issue.
   4.3 Run the reproduction script to confirm you are reproducing the issue.
   4.4 Adjust the reproduction script as necessary.

Phase 5. FIX ANALYSIS: state clearly the problem and how to fix it
   5.1 State clearly what the problem is.
   5.2 State clearly where the problem is located.
   5.3 State clearly how the test reproduces the issue.
   5.4 State clearly the best practices to take into account in the fix.
   5.5 State clearly how to fix the problem.

Phase 6. FIX IMPLEMENTATION: Edit the source code to implement your chosen solution.
   6.1 Make minimal, focused changes to fix the issue.

Phase 7. VERIFICATION: Test your implementation thoroughly.
   7.1 Run your reproduction script to verify the fix works.
   7.2 Add edge cases to your test script to ensure comprehensive coverage.
   7.3 Run existing tests related to the modified code to ensure you haven't broken anything.

Phase 8. FINAL REVIEW: Carefully re-read the problem description and compare your changes.
   8.1 Ensure you've fully addressed all requirements.
   8.2 Run any tests in the repository related to:
      8.2.1 The issue you are fixing
      8.2.2 The files you modified
      8.2.3 The functions you changed
   8.3 If any tests fail, revise your implementation until all tests pass.

Be thorough in your exploration, testing, and reasoning. It's fine if your thinking process is lengthy - quality and completeness are more important than brevity.

IMPORTANT CONSTRAINTS:
- ONLY modify files within the /testbed directory
- DO NOT navigate outside this directory (no `cd ..` or absolute paths to other locations)
- DO NOT create, modify, or delete any files outside the repository
- All your changes must be trackable by `git diff` within the repository
- If you need to create test files, create them inside the repository directory
