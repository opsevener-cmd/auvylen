const id = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const account = /^v1\/(auth\/(csrf|register|login|logout|me)|account|redeem|credit-products|credit-analyses(?:\/[0-9a-f-]+(?:\/result)?)?)$/;
const research = new RegExp(`^v1/research/(status|jobs(?:/${id}(?:/cancel)?)?|preferences/(models(?:/${id}/(?:edit|delete))?|train|predict|projects|datasets(?:/${id}(?:/(edit|delete|pairs|images(?:/${id}/(content|edit|rating|delete))?))?)?))$`);
export function allowedApiPath(path: string): boolean {
  return account.test(path) || research.test(path);
}
